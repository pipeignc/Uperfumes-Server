"""PARADIGMA ORIENTADO A OBJETOS: asistente local de recuperación con TF-IDF.

Composición (Chatbot → KnowledgeIndex), encapsulación del índice y
polimorfismo (FAQ / ficha de perfume). No usa un servicio generativo externo.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
import unicodedata

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .functional import format_clp, usd_to_clp


class KnowledgeEntry(ABC):
    @property
    @abstractmethod
    def searchable_text(self):
        """Texto con el que se entrena el índice local."""

    @abstractmethod
    def answer(self, rate):
        """Cada fuente resuelve cómo presentar su respuesta."""

    @property
    @abstractmethod
    def source(self):
        """Procedencia de la información."""


@dataclass(frozen=True)
class FAQ(KnowledgeEntry):
    question: str
    response: str
    reference: str = "Guía de UPerfumes"

    @property
    def searchable_text(self):
        return self.question

    def answer(self, rate):
        return self.response

    @property
    def source(self):
        return self.reference


@dataclass(frozen=True)
class PerfumeEntry(KnowledgeEntry):
    name: str
    price_usd: float

    @property
    def searchable_text(self):
        return f"{self.name} precio perfume información cuánto cuesta"

    def answer(self, rate):
        if rate is None:
            return (f"Tengo información de {self.name}. Ingresa el tipo de cambio USD a CLP "
                    "en la parte superior para mostrar su precio en pesos chilenos.")
        price = format_clp(usd_to_clp(self.price_usd, rate))
        return (f"{self.name}: {price} como precio referencial, usando {rate} CLP por USD. "
                "El precio proviene del dataset y su presentación no está especificada. "
                "Su disponibilidad en la tienda no está confirmada.")

    @property
    def source(self):
        return f"DATASET_PROTOTIPO · {self.name} · Precio_Real_USD"


FAQ_ENTRIES = (
    FAQ("hola buenos días buenas tardes saludos qué puedes hacer ayuda",
        "¡Hola! Puedo ayudarte con perfumes del dataset, sus precios referenciales en CLP, "
        "el recomendador y cómo funciona la compra. Por ejemplo: «¿Cuánto cuesta Sauvage EDP?»"),
    FAQ("recomendador cómo funciona el recomendador recomendar recomendación recomiéndame perfume elegir clima edad ocasión género presupuesto",
        "Abre «Encuentra tu perfume» y completa edad, clima, ocasión, presupuesto en CLP y género. "
        "El modelo compara tu perfil con lo aprendido del dataset y entrega sus tres sugerencias. "
        "Pueden incluir perfumes que la tienda todavía no vende."),
    FAQ("precio precios moneda pesos chilenos CLP USD dólar conversión tipo cambio",
        "Los precios del dataset están en USD. Multiplicamos Precio_Real_USD por la tasa que ingresas "
        "y redondeamos al peso más cercano. Son valores referenciales; no cotizaciones en tiempo real."),
    FAQ("pago pagar pagos webpay tarjeta transferencia métodos compra comprar",
        "La documentación de la tienda describe Webpay Plus y transferencia como métodos de pago. "
        "El chat no procesa pagos ni solicita datos de tarjetas.", "README.md · Cómo funciona la compra"),
    FAQ("carrito agregar producto formatos decant mililitros 3 ml 5 ml 10 ml",
        "Según la guía de la tienda, puedes elegir formatos de 3, 5 o 10 ml y agregarlos al carrito. "
        "El precio del dataset del recomendador no equivale al precio de un decant del catálogo.",
        "README.md · Cómo funciona la compra"),
    FAQ("envío despacho entrega demora días devolución devoluciones reembolso seguimiento pedido",
        "No tengo políticas de despacho, devoluciones ni acceso al estado de pedidos. "
        "Confirma esos datos directamente con la tienda antes de comprar."),
    FAQ("stock disponibilidad disponible inventario venden existe catálogo",
        "El recomendador explora el dataset completo. Que sugiera un perfume no confirma stock "
        "ni que esté a la venta. Revisa el catálogo de la tienda para comprar."),
    FAQ("comparar comparador barato económicos económica presupuesto alternativas filtrar ordenar",
        "En «Compara por presupuesto» puedes buscar un nombre y ver alternativas del dataset "
        "que caben en tu presupuesto, ordenadas de menor a mayor precio referencial en CLP."),
    FAQ("modelo machine learning random forest probabilidad puntaje puntuación certeza acierto confianza",
        "El recomendador usa Random Forest con cinco variables: edad, clima, ocasión, presupuesto y género. "
        "El puntaje ordena las sugerencias; no garantiza que un aroma te guste ni es una probabilidad calibrada."),
    FAQ("chatbot inteligencia artificial IA local funciona generativo internet claves api privacidad datos",
        "Soy un asistente local: uso TF-IDF y similitud de texto para recuperar respuestas de una base "
        "de conocimiento y del dataset. No soy un modelo generativo y no envío tus mensajes a una API. "
        "Si no encuentro información suficiente, te lo diré."),
)


class KnowledgeIndex:
    def __init__(self, entries):
        self._entries = tuple(entries)
        self._vectorizer = TfidfVectorizer(
            strip_accents="unicode", lowercase=True, ngram_range=(1, 2),
            stop_words=["de", "del", "el", "la", "los", "las", "un", "una", "y", "en", "por", "que", "es", "a"],
        )
        self._matrix = self._vectorizer.fit_transform(entry.searchable_text for entry in self._entries)

    def search(self, message):
        # Un precio solo se responde si el nombre está identificado; palabras
        # genéricas como «cuánto cuesta» no deben seleccionar un perfume al azar.
        def normalized(text):
            ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
            return " ".join(re.findall(r"[a-z0-9]+", ascii_text.casefold()))

        query = " " + normalized(message) + " "
        perfumes = tuple(entry for entry in self._entries if isinstance(entry, PerfumeEntry))
        exact = [entry for entry in perfumes if " " + normalized(entry.name) + " " in query
                 and len(normalized(entry.name)) > 2]
        # Por ejemplo, «Sauvage EDP» es más específico que «Sauvage».
        exact = [entry for entry in exact if not any(entry.name != other.name and
                 normalized(entry.name) in normalized(other.name) for other in exact)]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return FAQ("", "Encontré varios perfumes: " + ", ".join(entry.name for entry in exact[:5]) +
                       ". Pregúntame por uno a la vez o usa el comparador para ver precios.")

        vector = self._vectorizer.transform([message])
        scores = cosine_similarity(vector, self._matrix)[0]
        for index, entry in enumerate(self._entries):
            if isinstance(entry, PerfumeEntry):
                scores[index] = 0
        best = int(scores.argmax())
        if float(scores[best]) < 0.18:
            return None
        return self._entries[best]


class PerfumeChatbot:
    def __init__(self, index):
        self._index = index

    @classmethod
    def from_catalog(cls, catalog):
        entries = (*FAQ_ENTRIES, *(PerfumeEntry(p["name"], p["price_usd"]) for p in catalog))
        return cls(KnowledgeIndex(entries))

    def reply(self, message, history=(), rate=None):
        query = message.strip()
        # Contexto acotado para «¿y su precio?»; el cliente conserva la conversación.
        if query.casefold().startswith(("y ", "¿y ", "cuánto cuesta", "¿cuánto cuesta")) and len(query.split()) < 5:
            previous = next((item["content"] for item in reversed(history) if item["role"] == "user"), "")
            query = previous + " " + query
        entry = self._index.search(query)
        if entry is None:
            return {
                "answer": "No tengo información suficiente para responder eso. Puedes preguntarme por "
                          "un perfume concreto, precios en CLP, el recomendador o los métodos de pago.",
                "mode": "local_retrieval", "sources": [], "matched": False,
            }
        return {"answer": entry.answer(rate), "mode": "local_retrieval", "sources": [entry.source], "matched": True}
