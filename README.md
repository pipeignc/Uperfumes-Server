# UPerfumes — servidor

Backend en Node.js + Express para UPerfumes. Guarda los pedidos en una base
de datos SQLite y procesa los pagos con tarjeta mediante **Webpay Plus**
(Transbank), usando su SDK oficial. También sirve el sitio (carpeta
`public/`), así que todo corre desde un solo servidor y un solo puerto —
sin problemas de CORS entre frontend y backend.

La tienda tiene **catálogo, fichas de producto, carrito, "Comprar ahora" y
pago** (Webpay o transferencia).

## Requisitos

- Node.js 18 o superior (para correr el servidor)
- npm
- Para correr las pruebas (`npm test`): Node 22.22 o superior

## Instalación

```bash
cd server
npm install
cp .env.example .env
npm start
```

El servidor queda escuchando en `http://localhost:3000` (o el puerto que
pongas en `PORT`). La base de datos SQLite se crea sola la primera vez que
corre, en `data/uperfumes.sqlite`.

Para desarrollo, `npm run dev` reinicia el servidor solo cada vez que
guardas un archivo (usa `node --watch`).

## Probar todo automáticamente

```bash
npm test
```

Levanta el servidor, abre las páginas reales en un navegador simulado
(jsdom) y recorre el sitio: agregar al carrito, el panel lateral, la ficha
de producto, cambio de idioma y tema, el formulario de pago, el viaje
completo a Webpay (con la respuesta de Transbank simulada), pago aprobado,
rechazado, cancelado y montos que no coinciden. Usa una base de datos
temporal, no toca la tuya. Córrelo cada vez que cambies algo.

## Qué trae `.env.example`

Ya viene con las credenciales **públicas de prueba** que Transbank publica
para que cualquiera pueda integrar y probar Webpay Plus sin tener comercio
afiliado todavía (`TRANSBANK_COMMERCE_CODE` / `TRANSBANK_API_KEY` con
`TRANSBANK_ENVIRONMENT=integration`). Con eso el proyecto funciona en modo
prueba apenas lo instalas.

Para cobrar de verdad necesitas:

1. Afiliarte como comercio en Transbank (transbankdevelopers.cl) y que te
   aprueben Webpay Plus.
2. Reemplazar `TRANSBANK_COMMERCE_CODE` y `TRANSBANK_API_KEY` en tu `.env`
   por los de **producción** que te entregue Transbank.
3. Cambiar `TRANSBANK_ENVIRONMENT=production`.
4. Poner `PUBLIC_BASE_URL` con el dominio real donde quede publicado el
   servidor (Transbank necesita poder llamar de vuelta a esa URL).

`.env` nunca debe subirse a un repositorio — ya está en `.gitignore`.

## Estructura

```
server/
  src/
    server.js            # arranca el servidor
    app.js                # arma Express: seguridad, rutas, estáticos
    db/index.js            # SQLite: tablas orders y order_items (+ migración)
    data/catalog.js        # precios reales de cada perfume
    services/
      orders.js             # consultas a la base de datos
      webpay.js              # wrapper del SDK de Transbank
    routes/
      orders.js              # GET /api/catalog, POST /api/orders, GET /api/orders/:buyOrder
      webpay.js               # GET y POST /webpay/retorno (vuelta de Transbank)
    middleware/              # validación y manejo de errores
    utils/ids.js            # genera buyOrder y sessionId
  public/                 # el sitio
    index.html             # portada, recomendador, catálogo, panel "Comprar"
    producto.html / .js     # ficha de cada perfume
    carrito.html / .js      # página del carrito + pago
    pedido.html / .js       # "Comprar ahora" (un solo producto) + pago
    confirmacion.html / .js # resultado después de pagar con Webpay
    cart.js                # el carrito (estado + panel lateral + botón del HUB)
    checkout.js            # formulario de pago compartido (pedido y carrito)
    script.js, styles.css  # lógica y estilos generales
    images/                # TODAS las fotos (ver más abajo)
  test/e2e.js             # pruebas de punta a punta (npm test)
  data/                   # acá vive el archivo .sqlite (se crea solo)
```

## Las fotos (carpeta `public/images/`)

Cada perfume usa `images/<id>.jpg` en el catálogo, el carrito y su ficha:

`dior-sauvage-edt`, `invictus-victory-elixir`, `dior-homme-intense`,
`valentino-born-in-roma-extradose`, `jpg-le-male-elixir`,
`jpg-le-beau-le-parfum`, `jpg-le-male-le-parfum`, `mancera-cedrat-boise`,
`mykonos-inception`, `azzaro-most-wanted-intense`, `french-avenue-liquid-brun`
(800 × 1000 px). Mientras un archivo no exista se ve un recuadro punteado en
su lugar; en el carrito, la miniatura simplemente queda vacía. Además va
`hero-uperfumes.jpg` (la imagen principal de la portada).

## Cómo funciona la compra

**Agregar al carrito.** En el catálogo, al hacer clic en un formato (3, 5 o
10 ml) aparece el panel "Comprar" con dos botones: **Agregar al carrito** y
**Comprar ahora**. También se llega a cada perfume con un clic en su foto o
nombre: la ficha (`producto.html`) muestra la foto centrada y, a su derecha,
los formatos, la cantidad y esos mismos dos botones.

**El carrito.** Al agregar, se despliega un panel desde la derecha, pegado
al HUB, con lo que hay en el carrito. El botón del carrito vive en el HUB y
muestra cuántas unidades hay. Desde el panel, **Ir a carrito** lleva a
`carrito.html`, donde se ve la lista completa, el total y el pago. El
carrito se guarda en el navegador (`localStorage`), así que sobrevive al
cambiar de página. También se recuerdan el idioma y el modo claro/oscuro.

**Pagar.** Desde el carrito (o desde "Comprar ahora", que paga un solo
producto sin tocar el carrito) la persona completa sus datos y elige:

- **Webpay** (por defecto): el navegador manda el pedido a
  `POST /api/orders`; el servidor lo guarda con todos sus ítems, crea la
  transacción en Transbank y devuelve un `token` y una `url`. Transbank exige
  llegar a esa URL con un **POST** (no con un link normal), por eso las
  páginas traen un formulario oculto que se completa y envía solo.
- **Transferencia**: se guarda el pedido y se muestran los datos bancarios y
  el monto a transferir.

**La vuelta de Transbank** llega a `/webpay/retorno`, que:

- si trae `token_ws`, confirma la transacción (`commit`), verifica que el
  monto cobrado sea exactamente el del pedido, guarda el resultado
  (aprobado/rechazado, código de autorización, últimos 4 dígitos) y
  redirige a `confirmacion.html`. Si la persona recarga esa página, no
  vuelve a confirmar: muestra el resultado ya guardado.
- si llega sin `token_ws` (se arrepintió o se acabó el tiempo), **no**
  confirma nada — Transbank no lo permite en ese estado — y marca el pedido
  como cancelado.

El carrito se **vacía solo cuando el pedido queda cerrado**: al confirmar una
transferencia, o al volver aprobado desde Webpay. Si el pago se rechaza o se
cancela, el carrito se conserva para reintentar.

## Seguridad: qué ya está cubierto

- **Nunca se confía en el precio del navegador.** El carrito, la ficha y las
  páginas de pago solo *muestran* precios (los pide a `GET /api/catalog`);
  al crear el pedido, el servidor recalcula cada línea con su propio
  catálogo (`src/data/catalog.js`). Aunque alguien manipule la petición,
  paga el monto real.
- Se valida todo (perfume, formato 3/5/10 ml, cantidad 1–10, máximo 20
  líneas, correo, dirección) y los ítems repetidos se suman.
- Encabezados de seguridad (`helmet`), límite de 30 pedidos cada 10 minutos
  por IP (`express-rate-limit`).
- Detrás del proxy de un hosting hay que dejar `TRUST_PROXY=1` (ya viene así
  en `.env.example`); sin eso, todos los clientes compartirían el mismo
  límite.
- El servidor nunca ve ni guarda el número de tarjeta: Webpay Plus es un
  formulario alojado por Transbank; acá solo llegan los últimos 4 dígitos.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/catalog` | Catálogo público (casa, nombre, formato y precios). |
| POST | `/api/orders` | Crea un pedido con uno o varios ítems (`items: [{perfumeId, ml, qty}]`). Si es por Webpay, también crea la transacción en Transbank. |
| GET | `/api/orders/:buyOrder` | Estado y datos públicos de un pedido (con sus ítems). |
| GET / POST | `/webpay/retorno` | URL de retorno registrada ante Transbank. No se llama a mano. |
| GET | `/health` | Monitoreo: responde `{"ok":true}`. |

## Si ya tenías una base de datos de la versión anterior

No tienes que hacer nada: al arrancar, el servidor detecta el esquema viejo
(un perfume por pedido), pasa esos pedidos a la tabla `order_items` y sigue.

## Ver los pedidos guardados

```bash
sqlite3 data/uperfumes.sqlite "SELECT buy_order, status, amount, customer_name, created_at FROM orders ORDER BY id DESC;"
sqlite3 data/uperfumes.sqlite "SELECT o.buy_order, i.house, i.name, i.ml, i.qty, i.unit_price FROM order_items i JOIN orders o ON o.id = i.order_id ORDER BY o.id DESC;"
```

Estados de un pedido: `pending_webpay`, `pending_transfer`, `approved`,
`rejected`, `cancelled`, `failed` (Transbank no respondió al crear el pago) y
`amount_mismatch` (el monto cobrado no coincidía con el del pedido; no se da
por pagado).

## Publicarlo (producción)

Esto no es un sitio estático: necesita un proceso de Node corriendo
(Railway, Render, Fly.io, o un VPS con PM2).

1. Sube esta carpeta `server/` (con `public/` adentro).
2. Configura las variables del `.env` en el panel del hosting (no subas el
   archivo `.env`).
3. Define `PUBLIC_BASE_URL` con la URL real que te den, y
   `DATABASE_PATH` apuntando a un **volumen persistente** (por ejemplo
   `/data/uperfumes.sqlite`); si no, la base se pierde en cada despliegue.
4. Antes de cobrar de verdad, cambia a tus credenciales de producción de
   Transbank y `TRANSBANK_ENVIRONMENT=production`.

## Pendiente si esto se pone en producción real

- Los datos de `TRANSFER_DETAILS` en `src/routes/orders.js` son de ejemplo —
  reemplázalos por los reales.
- No hay panel de administración para marcar un pedido por transferencia
  como pagado: por ahora se hace a mano en la base de datos.
- No se envían correos (confirmación al cliente, aviso a la tienda). Se
  podría agregar con un servicio como Resend o un SMTP propio; no se incluyó
  porque requiere credenciales reales.
- El carrito vive en el navegador de cada persona: si cambia de dispositivo
  no lo lleva consigo. Si más adelante quieres cuentas de usuario, este es el
  punto a evolucionar.
