from typing import NamedTuple, List, Dict, DefaultDict, Tuple

import json
import functools
from datetime import datetime, timezone
from urllib.parse import unquote
import logging
from collections import defaultdict
import requests
from lxml import etree # type: ignore[import]
from ..utils.utils import retry


LOGGER = logging.getLogger('__name__')


class Product(NamedTuple):
    brand: str
    model: str
    condition: str
    link: str

class Variant(NamedTuple):
    spec: str
    color: str
    # OutOfStock, InStock, PreOrder
    stock: str
    cash_price: int
    rrp: int

class ProductVariant(NamedTuple):
    brand: str
    model: str
    spec: str
    color: str
    condition: str
    stock: str
    cash_price: int
    rrp: int
    link: str


def parse_link(link: str) -> str:
    # /shop/samsung/galaxy-s20-ultra-5g#contractType=paymonthly
    *_, _, model_part = link.split('/')
    model, _ = model_part.split('#', 1)
    model = model.replace('-like-new', '')
    return model


def fix_link(link: str) -> str:
    link = link.replace('/shop', '/shop/tariff')
    return link


def parse_spec(spec: str) -> Tuple[str, str]:
    # connectivity:N/A_colour:black_memory:64gb
    color = ''

    spec_list = []
    for x in spec.split('_'):
        if x == 'connectivity:N/A':
            continue
        k, v = x.split(':')
        if k == 'colour':
            color = v
            continue
        spec_list.append(x)

    return color, ' '.join(spec_list)


def fetch_products() -> List[Product]:
    url = 'https://www.o2.co.uk/shop/phones'
    r = requests.get(url)
    r.raise_for_status()
    tree = etree.HTML(r.text)
    products = []
    # Faster to ignore the this extra condition
    # //div[@component-name="productTile"]
    for x in tree.xpath('//a[contains(@class, "device-tile")]'):
        link = x.attrib['href']
        model = parse_link(link)
        products.append(Product(
            brand=x.attrib['data-qa-device-brand'],
            model=model,
            condition=x.attrib['data-qa-device-condition'],
            link=fix_link(link),
        ))
    return products


def parse_product_details(details: str) -> List[Variant]:
    variants = json.loads(json.loads(details)['o2_theme']['ProductDetails'])['deviceInfoV2']['variants']
    ret = []
    for key, value in variants.items():
        color, spec = parse_spec(unquote(key))
        ret.append(Variant(
            spec=spec,
            color=color,
            stock=value['stockInfo']['stock'],
            cash_price=value['cashPrice']['oneOff'],
            rrp= value['rrp']['oneOff']
        ))
    return ret


def fetch_variants(session: requests.Session, product: Product) -> List[ProductVariant]:
    link = product.link
    r = session.get('https://www.o2.co.uk/' + link)
    r.raise_for_status()
    tree = etree.HTML(r.text)
    json_str, = tree.xpath('//script[@data-drupal-selector="drupal-settings-json"]/text()')
    variants = parse_product_details(json_str)

    product_variants = [
        ProductVariant(
            brand=product.brand,
            model=product.model,
            spec=variant.spec,
            color=variant.color,
            condition=product.condition,
            stock=variant.stock,
            cash_price=variant.cash_price,
            rrp=variant.rrp,
            link=link,
        )
        for variant in variants]
    return product_variants


def fetch_all_variants(products: List[Product]) -> List[ProductVariant]:
    ret = []
    session = requests.Session()
    for product in products:
        LOGGER.info(f'Fetching {product.link}')

        try:
            product_variants = retry(functools.partial(fetch_variants, session, product), 3)
            ret.extend(product_variants)
        except Exception:
            LOGGER.exception(f'Error at fetching {product.link}')
            continue
    return ret


def get_previous_deals_from_db(collection) -> Dict:
    return {(x['brand'], x['model'], x['spec'], x['condition']): x for x in collection.find()}


def rewrite_deals_to_db(deals: Dict[Tuple, ProductVariant], collection) -> None:
    LOGGER.info('Rewriting to db')
    collection.drop()
    collection.insert_many([deal._asdict() for deal in deals.values()])



def report_best_value(collection, product_variants: List[ProductVariant], n: int) -> str:
    # For used phones, rrp is lower, sometime it is even lower than cash price.
    # Use new phone rrp as reference if possible.
    reference_price: DefaultDict[Tuple[str, str, str], int] = defaultdict(int)

    def get_key_for_model(x: ProductVariant):
        return x.brand, x.model, x.spec

    for x in product_variants:
        key = get_key_for_model(x)
        reference_price[key] = max(reference_price[key], x.rrp)

    xs = [(reference_price[get_key_for_model(x)], x) for x in product_variants if x.stock != 'OutOfStock']
    xs.sort(key=lambda x: x[1].cash_price / x[0])

    def get_key_for_price(x: ProductVariant):
        # Only consider the best price for each key.
        # We don't want duplicate, e.g. different color of the same price.
        return x.brand, x.model, x.spec, x.condition

    previous_deals = get_previous_deals_from_db(collection)

    lines = [f'Update from Best {n} Deals']
    i = 0
    deals = {}
    for ref_price, x in xs:
        if i >= n:
            break

        key = get_key_for_price(x)
        if key in deals:
            # This is a worse alternative, ignore.
            continue

        deals[key] = x
        i += 1
        previous_deal = previous_deals.get(key)
        if previous_deal is not None:
            previous_price = previous_deal['cash_price']
            if x.cash_price == previous_price:
                # We have seen it before
                continue
            else:
                # Price update
                line = f'-- {x.brand:<10} {x.model:<20} {x.spec:<20} {x.condition:<8} £{x.cash_price / 100:<6g} (£{previous_price / 100:<6g}) £{ref_price / 100:<6g} {x.cash_price / ref_price:.2%}    -- {x.link}'
                lines.append(line)
                continue
        else:
            # New deal
            line = f'-- {x.brand:<10} {x.model:<20} {x.spec:<20} {x.condition:<8} £{x.cash_price / 100:<6g} £{ref_price / 100:<6g} {x.cash_price / ref_price:.2%}    -- {x.link}'
            lines.append(line)
            continue
    # I don't care if previous_deals have gone disappeared.

    if len(lines) > 1:
        # It always has 1 line of header.
        rewrite_deals_to_db(deals, collection)
        return '\n'.join(lines)
    else:
        return ''


def pipeline(db) -> str:
    products = fetch_products()
    product_variants = fetch_all_variants(products)

    best_value = report_best_value(db.o2_phones, product_variants, 10)
    if best_value:
        return f'Sent at {datetime.now(timezone.utc)}\n\n{best_value}'
    else:
        return ''

