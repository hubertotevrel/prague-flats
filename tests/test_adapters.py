#!/usr/bin/env python3
"""Adapter parsing tests (offline — no network). Validates the pure mapping/parsing
logic of the Bezrealitky and iDnes adapters against fixtures."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup                       # noqa: E402
from pragueflats.portals import bezrealitky, idnes  # noqa: E402


def check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise AssertionError(label)


def test_bezrealitky():
    print("Bezrealitky parsing")
    check("zip 140 00 -> Praha 4", bezrealitky._district_from_zip("140 00") == "Praha 4")
    check("zip 100 00 -> Praha 10", bezrealitky._district_from_zip("100 00") == "Praha 10")
    check("zip 170 00 -> Praha 7", bezrealitky._district_from_zip("170 00") == "Praha 7")
    check("zip None -> None", bezrealitky._district_from_zip(None) is None)

    advert = {
        "id": "1036171", "uri": "1036171-nabidka-pronajem-bytu-nuselska-praha",
        "price": 23300, "charges": 4800, "surface": 42, "disposition": "DISP_2_KK",
        "street": "Nuselská", "houseNumber": "69/28", "city": "Praha",
        "cityDistrict": "Praha - Nusle", "zip": "140 00",
        "gps": {"lat": 50.0625, "lng": 14.4441},
    }
    rl = bezrealitky._to_raw(advert)
    check("disposition DISP_2_KK -> 2+kk", rl.disposition == "2+kk")
    check("real charges carried (4800)", rl.charges_czk == 4800)
    check("district from zip -> Praha 4", rl.district == "Praha 4")
    check("gps mapped (lng->longitude)", rl.latitude == 50.0625 and rl.longitude == 14.4441)
    check("url built", rl.url == bezrealitky.DETAIL_BASE + advert["uri"])
    check("not agency (direct landlord)", rl.is_agency is False)


CARD_HTML = """
<li class="c-products__item">
  <a class="c-products__link"
     href="https://reality.idnes.cz/detail/pronajem/byt/praha-1-truhlarska/69fc5f7e571cf680b9086a35/">
    <span class="c-products__title">pronájem bytu 3+kk 123 m²</span>
  </a>
  <p class="c-products__price">63 000 Kč/měsíc</p>
  <p class="c-products__info">Truhlářská, Praha 1 - Nové Město, okres Praha</p>
</li>
"""


def test_idnes():
    print("iDnes parsing")
    card = BeautifulSoup(CARD_HTML, "lxml").select_one(".c-products__item")
    rl = idnes._parse_card(card)
    check("disposition 3+kk", rl.disposition == "3+kk")
    check("area 123", rl.area_m2 == 123.0)
    check("price 63000", rl.price_czk == 63000)
    check("district Praha 1", rl.district == "Praha 1")
    check("city_part Nové Město", rl.city_part == "Nové Město")
    check("street Truhlářská", rl.street == "Truhlářská")
    check("source_id = url hash", rl.source_id == "69fc5f7e571cf680b9086a35")
    check("no coords (geocoded later)", rl.latitude is None and rl.longitude is None)


def main():
    test_bezrealitky()
    test_idnes()
    print("\nALL ADAPTER CHECKS PASSED")


if __name__ == "__main__":
    main()
