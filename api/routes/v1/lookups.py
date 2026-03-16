from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/v1/lookups", tags=["lookups"])


INDIA_STATES_AND_UTS = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]


INDIA_UNITS = [
    "Nos",
    "Piece",
    "Pair",
    "Set",
    "Dozen",
    "Box",
    "Packet",
    "Bag",
    "Bottle",
    "Can",
    "Carton",
    "Case",
    "Roll",
    "Bundle",
    "Sheet",
    "Kg",
    "Gram",
    "Mg",
    "Quintal",
    "Tonne",
    "Litre",
    "Ml",
    "Meter",
    "Cm",
    "Mm",
    "Km",
    "Foot",
    "Inch",
    "Square Foot",
    "Square Meter",
    "Cubic Foot",
    "Cubic Meter",
]


class IndiaLookupsOut(BaseModel):
    states: list[str]
    units: list[str]


@router.get("/india", response_model=IndiaLookupsOut)
def get_india_lookups() -> IndiaLookupsOut:
    return IndiaLookupsOut(
        states=INDIA_STATES_AND_UTS,
        units=INDIA_UNITS,
    )
