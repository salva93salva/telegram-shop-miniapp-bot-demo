'use client';

import Image from 'next/image';
import Script from 'next/script';
import {
  ArrowRight,
  Check,
  Download,
  Minus,
  Package,
  Plus,
  Search,
  Settings,
  ShoppingBag,
  Sparkles,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';

type Category = 'Digitali' | 'Fisici';

type Product = {
  id: number;
  name: string;
  category: Category;
  description: string;
  price: string;
  icon: LucideIcon;
  tone: string;
  available: boolean;
  stockQuantity: number | null;
  photoUrl: string | null;
};

type ApiProduct = {
  id: number;
  name: string;
  description: string;
  product_type: 'digital' | 'physical';
  price: { label: string };
  stock_quantity: number | null;
  available: boolean;
  photo_url: string | null;
};

type CatalogResponse = {
  shop_name: string;
  products: ApiProduct[];
};

type ToolDefinition = {
  name: string;
  title?: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations?: {
    readOnlyHint?: boolean;
    untrustedContentHint?: boolean;
  };
  execute: (input: unknown) => unknown | Promise<unknown>;
};

declare global {
  interface Document {
    modelContext?: {
      registerTool: (
        tool: ToolDefinition,
        options?: { signal?: AbortSignal },
      ) => void | Promise<void>;
    };
  }

  interface Window {
    Telegram?: {
      WebApp: {
        initData: string;
        ready: () => void;
        expand: () => void;
        openTelegramLink: (url: string) => void;
        HapticFeedback?: {
          notificationOccurred: (type: 'success' | 'error') => void;
        };
      };
    };
  }
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  'https://telegram-shop-miniapp-bot-demo-production.up.railway.app';
const CATALOG_URL = `${API_BASE_URL}/api/catalog`;

function mapApiProduct(product: ApiProduct): Product {
  const isDigital = product.product_type === 'digital';

  return {
    id: product.id,
    name: product.name,
    category: isDigital ? 'Digitali' : 'Fisici',
    description: product.description,
    price: product.price.label,
    icon: isDigital ? Download : Package,
    tone: isDigital
      ? 'from-cyan-400/30 via-blue-500/10 to-transparent'
      : 'from-blue-500/30 via-cyan-400/10 to-transparent',
    available: product.available,
    stockQuantity: product.stock_quantity,
    photoUrl: product.photo_url ? `${API_BASE_URL}${product.photo_url}` : null,
  };
}

function parseToolProductId(input: unknown): number {
  if (
    typeof input !== 'object' ||
    input === null ||
    !('productId' in input) ||
    typeof input.productId !== 'number' ||
    !Number.isInteger(input.productId)
  ) {
    throw new Error('productId deve essere un numero intero.');
  }

  return input.productId;
}

export default function Home() {
  const [products, setProducts] = useState<Product[]>([]);
  const [shopName, setShopName] = useState('ShopBot Mini App Demo');
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<'Tutti' | Category>('Tutti');
  const [cart, setCart] = useState<Record<number, number>>({});
  const [checkoutMessage, setCheckoutMessage] = useState('');
  const [checkoutState, setCheckoutState] = useState<
    'idle' | 'loading' | 'success' | 'error'
  >('idle');
  const [telegramReady, setTelegramReady] = useState(false);

  const productsRef = useRef(products);
  const cartRef = useRef(cart);

  useEffect(() => {
    productsRef.current = products;
  }, [products]);

  useEffect(() => {
    cartRef.current = cart;
  }, [cart]);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError('');

    try {
      const response = await fetch(CATALOG_URL, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`Catalog request failed: ${response.status}`);
      }

      const catalog = (await response.json()) as CatalogResponse;
      setShopName(catalog.shop_name);
      setProducts(catalog.products.map(mapApiProduct));
    } catch (error) {
      console.error('Catalog loading failed', error);
      setCatalogError(
        'Il catalogo non è disponibile in questo momento. Riprova tra poco.',
      );
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const visibleProducts = useMemo(
    () =>
      products.filter((product) => {
        const matchesCategory =
          category === 'Tutti' || product.category === category;
        const matchesQuery = product.name
          .toLowerCase()
          .includes(query.toLowerCase());
        return matchesCategory && matchesQuery;
      }),
    [category, products, query],
  );

  const cartItems = useMemo(
    () =>
      products
        .filter((product) => cart[product.id])
        .map((product) => ({
          product,
          quantity: cart[product.id],
        })),
    [cart, products],
  );

  const cartCount = cartItems.reduce((total, item) => total + item.quantity, 0);

  const addToCart = useCallback((productId: number) => {
    if (!productsRef.current.some((product) => product.id === productId)) {
      throw new Error('Prodotto non trovato.');
    }

    setCart((current) => ({
      ...current,
      [productId]: (current[productId] ?? 0) + 1,
    }));
    setCheckoutMessage('');
  }, []);

  const changeQuantity = (productId: number, delta: number) => {
    setCart((current) => {
      const nextQuantity = (current[productId] ?? 0) + delta;
      const next = { ...current };

      if (nextQuantity <= 0) {
        delete next[productId];
      } else {
        next[productId] = nextQuantity;
      }

      return next;
    });
    setCheckoutMessage('');
  };

  const handleTelegramReady = useCallback(() => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) return;
    webApp.ready();
    webApp.expand();
    setTelegramReady(true);
  }, []);

  useEffect(() => {
    handleTelegramReady();
  }, [handleTelegramReady]);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;

    const lifecycle = new AbortController();
    const reportError = (error: unknown) => {
      console.error('WebMCP registration failed', error);
    };

    const addTool: ToolDefinition = {
      name: 'add_product_to_cart',
      title: 'Aggiungi prodotto al carrello',
      description:
        'Aggiunge al carrello della Mini App un prodotto esistente tramite ID.',
      inputSchema: {
        type: 'object',
        properties: {
          productId: { type: 'integer', minimum: 1 },
        },
        required: ['productId'],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute(input) {
        const productId = parseToolProductId(input);
        addToCart(productId);
        return { productId, status: 'added' };
      },
    };

    const readTool: ToolDefinition = {
      name: 'read_cart',
      title: 'Leggi carrello',
      description: 'Restituisce il numero totale di articoli nel carrello.',
      inputSchema: {
        type: 'object',
        properties: {},
        additionalProperties: false,
      },
      annotations: { readOnlyHint: true, untrustedContentHint: false },
      execute() {
        const itemCount = Object.values(cartRef.current).reduce(
          (total, quantity) => total + quantity,
          0,
        );
        return { itemCount };
      },
    };

    for (const tool of [addTool, readTool]) {
      try {
        void Promise.resolve(
          context.registerTool(tool, { signal: lifecycle.signal }),
        ).catch(reportError);
      } catch (error) {
        reportError(error);
      }
    }

    return () => lifecycle.abort();
  }, [addToCart]);

  const completeCheckout = async () => {
    if (!cartCount || checkoutState === 'loading') return;

    const webApp = window.Telegram?.WebApp;

    if (!webApp?.initData) {
      setCheckoutState('error');
      setCheckoutMessage(
        'Apri questa Mini App dal bot Telegram per continuare il checkout.',
      );
      return;
    }

    setCheckoutState('loading');
    setCheckoutMessage('Trasferimento sicuro del carrello al bot...');

    try {
      const response = await fetch(`${API_BASE_URL}/api/cart/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Telegram-Init-Data': webApp.initData,
        },
        body: JSON.stringify({
          items: cartItems.map(({ product, quantity }) => ({
            product_id: product.id,
            quantity,
          })),
        }),
      });
      const result = (await response.json()) as {
        detail?: string;
        bot_url?: string;
      };

      if (!response.ok || !result.bot_url) {
        throw new Error(result.detail || 'Checkout non disponibile.');
      }

      setCheckoutState('success');
      setCheckoutMessage(
        'Carrello trasferito. Nel bot trovi i pulsanti per completare l’ordine.',
      );
      setCart({});
      webApp.HapticFeedback?.notificationOccurred('success');
      webApp.openTelegramLink(result.bot_url);
    } catch (error) {
      setCheckoutState('error');
      setCheckoutMessage(
        error instanceof Error
          ? error.message
          : 'Checkout non disponibile. Riprova tra poco.',
      );
      webApp.HapticFeedback?.notificationOccurred('error');
    }
  };

  return (
    <main className="miniapp-shell min-h-screen overflow-x-hidden text-white">
      <Script
        src="https://telegram.org/js/telegram-web-app.js"
        strategy="afterInteractive"
        onLoad={handleTelegramReady}
      />
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <div className="flex items-center gap-3">
          <div className="brand-orbit">
            <Image
              src="/shop-bot-profile.png"
              width={42}
              height={42}
              alt="ShopBot"
              priority
              className="rounded-xl"
            />
          </div>
          <div>
            <p className="text-sm font-black tracking-wide">SHOPBOT</p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300/70">
              Mini App Store
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Dialog>
            <DialogTrigger
              render={
                <Button
                  variant="outline"
                  size="icon-lg"
                  aria-label="Gestisci prodotti"
                  className="border-blue-300/20 bg-[#081835]/80 text-cyan-100 hover:bg-blue-500/15"
                />
              }
            >
              <Settings />
            </DialogTrigger>
            <DialogContent className="admin-dialog max-h-[88vh] overflow-y-auto border-blue-300/20 bg-[#061126] text-white sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle className="text-xl font-black">
                  Catalogo sincronizzato
                </DialogTitle>
                <DialogDescription className="text-slate-400">
                  I prodotti vengono gestiti dal pannello amministratore del bot
                  e compaiono automaticamente in questa Mini App.
                </DialogDescription>
              </DialogHeader>

              <div className="mt-5 space-y-2">
                {products.map((product) => (
                  <div key={product.id} className="admin-product-row">
                    <div className="min-w-0">
                      <p className="truncate font-bold">{product.name}</p>
                      <p className="text-xs text-slate-500">
                        {product.category} · {product.price}
                      </p>
                    </div>
                    <Badge className="bg-blue-500/10 text-cyan-200">
                      {product.stockQuantity === null
                        ? 'Digitale'
                        : `${product.stockQuantity} disponibili`}
                    </Badge>
                  </div>
                ))}
              </div>

              <Button
                onClick={() => void loadCatalog()}
                className="mt-3 bg-blue-600 text-white hover:bg-blue-500"
              >
                Aggiorna catalogo
              </Button>
            </DialogContent>
          </Dialog>

          <Sheet>
            <SheetTrigger
              render={
                <button
                  type="button"
                  aria-label={`Apri il carrello, ${cartCount} prodotti`}
                  className="cart-button"
                />
              }
            >
              <ShoppingBag className="size-5" />
              <span>Carrello</span>
              <strong>{cartCount}</strong>
            </SheetTrigger>
            <SheetContent
              side="right"
              className="cart-sheet w-[92%] border-blue-300/20 bg-[#051025] text-white sm:max-w-md"
            >
              <SheetHeader className="border-b border-white/5 p-5">
                <SheetTitle className="text-xl font-black text-white">
                  Il tuo carrello
                </SheetTitle>
                <SheetDescription className="text-slate-400">
                  {cartCount
                    ? `${cartCount} articoli pronti per l’ordine`
                    : 'Il carrello è ancora vuoto'}
                </SheetDescription>
              </SheetHeader>

              <div className="flex-1 space-y-3 overflow-y-auto px-5 py-3">
                {cartItems.map(({ product, quantity }) => (
                  <div key={product.id} className="cart-row">
                    <div className="cart-product-icon">
                      <product.icon className="size-5 text-cyan-200" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold">
                        {product.name}
                      </p>
                      <p className="text-xs text-cyan-300">{product.price}</p>
                    </div>
                    <div className="quantity-control">
                      <button
                        type="button"
                        onClick={() => changeQuantity(product.id, -1)}
                        aria-label={`Riduci quantità di ${product.name}`}
                      >
                        <Minus />
                      </button>
                      <span>{quantity}</span>
                      <button
                        type="button"
                        onClick={() => changeQuantity(product.id, 1)}
                        aria-label={`Aumenta quantità di ${product.name}`}
                      >
                        <Plus />
                      </button>
                    </div>
                  </div>
                ))}

                {!cartCount && (
                  <div className="cart-empty">
                    <ShoppingBag className="size-9 text-blue-300" />
                    <p>Scegli un prodotto dal catalogo.</p>
                  </div>
                )}

                {checkoutMessage && (
                  <div
                    className={`checkout-success ${
                      checkoutState === 'error' ? 'checkout-error' : ''
                    }`}
                    role={checkoutState === 'error' ? 'alert' : 'status'}
                  >
                    <Check className="size-5" />
                    <p>{checkoutMessage}</p>
                  </div>
                )}
              </div>

              <SheetFooter className="border-t border-white/5 p-5">
                <Button
                  onClick={() => void completeCheckout()}
                  disabled={!cartCount || checkoutState === 'loading'}
                  className="h-12 w-full rounded-xl bg-blue-600 text-base font-bold text-white shadow-[0_10px_32px_rgba(37,99,235,.32)] hover:bg-blue-500"
                >
                  {checkoutState === 'loading'
                    ? 'Preparazione checkout...'
                    : 'Continua nel bot'}{' '}
                  <ArrowRight data-icon="inline-end" />
                </Button>
                <p className="text-center text-[10px] text-slate-600">
                  Identità verificata da Telegram · pagamento demo
                </p>
              </SheetFooter>
            </SheetContent>
          </Sheet>
        </div>
      </header>

      <section className="relative z-10 mx-auto w-full max-w-6xl px-5 pb-10 pt-6 sm:px-8 sm:pt-10">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className="border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-cyan-200">
            <Sparkles data-icon="inline-start" /> Demo interattiva
          </Badge>
          {telegramReady && (
            <Badge className="border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-emerald-200">
              Telegram collegato
            </Badge>
          )}
        </div>

        <div className="mt-5 grid items-end gap-6 md:grid-cols-[1.15fr_0.85fr]">
          <div>
            <h1 className="max-w-2xl text-4xl font-black leading-[0.98] tracking-[-0.05em] sm:text-6xl">
              Il tuo store,
              <span className="gradient-title block">dentro Telegram.</span>
            </h1>
            <p className="mt-5 max-w-xl text-sm leading-6 text-slate-300 sm:text-base">
              Prodotti digitali e fisici in un&apos;esperienza veloce, moderna e
              pensata per lo smartphone.
            </p>
          </div>

          <div className="search-panel">
            <Search className="size-5 text-cyan-300" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Cerca nel catalogo..."
              aria-label="Cerca prodotti"
              className="h-11 border-0 bg-transparent px-1 text-white placeholder:text-slate-500 focus-visible:ring-0"
            />
          </div>
        </div>

        <nav
          className="mt-8 flex gap-2 overflow-x-auto pb-2"
          aria-label="Categorie"
        >
          {(['Tutti', 'Digitali', 'Fisici'] as const).map((item) => (
            <button
              type="button"
              key={item}
              onClick={() => setCategory(item)}
              className={`category-chip ${category === item ? 'is-active' : ''}`}
            >
              {item}
            </button>
          ))}
        </nav>

        <div className="mt-5 flex items-center justify-between">
          <div>
            <p className="text-lg font-bold">In evidenza</p>
            <p className="text-xs text-slate-500">{shopName}</p>
          </div>
          <span className="text-xs font-semibold text-cyan-300">
            {visibleProducts.length} prodotti
          </span>
        </div>

        {catalogLoading && (
          <div className="empty-state" role="status">
            <Sparkles className="size-6 animate-pulse text-cyan-300" />
            <p>Caricamento del catalogo...</p>
          </div>
        )}

        {catalogError && (
          <div className="empty-state" role="alert">
            <Package className="size-6 text-cyan-300" />
            <p>{catalogError}</p>
            <Button
              onClick={() => void loadCatalog()}
              className="bg-blue-600 text-white hover:bg-blue-500"
            >
              Riprova
            </Button>
          </div>
        )}

        {!catalogLoading && !catalogError && (
          <section
            className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
            aria-label="Catalogo prodotti"
          >
            {visibleProducts.map((product) => {
              const Icon = product.icon;
              return (
                <article key={product.id} className="product-card group">
                  <div
                    className={`product-visual bg-gradient-to-br ${product.tone}`}
                  >
                    {product.photoUrl ? (
                      <>
                        <span
                          role="img"
                          aria-label={product.name}
                          className="product-photo"
                          style={{
                            backgroundImage: `url("${product.photoUrl}")`,
                            backgroundPosition: 'center',
                            backgroundRepeat: 'no-repeat',
                            backgroundSize: 'contain',
                          }}
                        />
                        <span className="product-photo-shade" />
                      </>
                    ) : (
                      <>
                        <span className="visual-ring" />
                        <Icon className="relative z-10 size-16 stroke-[1.25] text-cyan-100 drop-shadow-[0_0_18px_rgba(34,211,238,.55)]" />
                      </>
                    )}
                    <Badge className="absolute left-3 top-3 bg-[#07152d]/75 text-cyan-100 backdrop-blur-md">
                      {product.category}
                    </Badge>
                  </div>

                  <div className="p-4">
                    <h2 className="text-base font-bold tracking-tight">
                      {product.name}
                    </h2>
                    <p className="mt-1 min-h-10 text-xs leading-5 text-slate-400">
                      {product.description}
                    </p>
                    <div className="mt-4 flex items-center justify-between gap-3">
                      <span className="text-lg font-black text-white">
                        {product.price}
                      </span>
                      <Button
                        onClick={() => addToCart(product.id)}
                        disabled={!product.available}
                        aria-label={`Aggiungi ${product.name} al carrello`}
                        className="h-10 rounded-xl bg-blue-600 px-3 text-white shadow-[0_8px_24px_rgba(37,99,235,.3)] hover:bg-blue-500"
                      >
                        <Plus />
                        <span className="sr-only">Aggiungi</span>
                      </Button>
                    </div>
                  </div>
                </article>
              );
            })}
          </section>
        )}

        {!catalogLoading && !catalogError && visibleProducts.length === 0 && (
          <div className="empty-state">
            <Search className="size-6 text-cyan-300" />
            <p>Nessun prodotto trovato. Prova un&apos;altra ricerca.</p>
          </div>
        )}
      </section>

      <footer className="relative z-10 border-t border-white/5 px-5 py-6 text-center text-[11px] text-slate-600">
        Mini App collegata al bot · checkout in modalità demo
      </footer>
    </main>
  );
}
