"""Product listing data model."""

from dataclasses import dataclass


@dataclass
class Product:
    price: float
    title: str
    description: str
    location: str
    date: str
    url: str
    img: str