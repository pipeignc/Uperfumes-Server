"""Contrato compartido con las codificaciones reales del notebook."""

FEATURES = ("Edad", "Clima_Cod", "Ocasion_Cod", "Presupuesto_USD", "Genero_Cod")
TARGET = "Perfume_Recomendado"
PRICE = "Precio_Real_USD"
CLIMATES = {
    "Cálido/Tropical": 1, "Templado": 2, "Frío": 3,
    "Húmedo": 4, "Árido/Desértico": 5,
}
OCCASIONS = {
    "Diario/Casual": 1, "Oficina/Trabajo": 2, "Formal/Noche": 3,
    "Fiesta/Salida nocturna": 4, "Deportivo/Ejercicio": 5,
    "Cita romántica": 6, "Evento especial/Boda": 7,
}
# La interfaz usa etiquetas, evitando confundir 0/1 del ejemplo con 1/2/3 del CSV.
GENDERS = {"Masculino": 1, "Femenino": 2, "Unisex": 3}
