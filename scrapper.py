from datetime import datetime
from re import search
from typing import NamedTuple, List
import traceback
import re

import pygsheets
import requests
from bs4 import BeautifulSoup

# https://console.cloud.google.com/apis/api/sheets.googleapis.com/credentials
gsheet_policy_json = '/Users/DTVD/Private/OrakaroDev/keibai/keibai-432201-d567755562ba.json'
result_sheet_name = 'Keibai Search Result'
# Keibai Search Result: https://docs.google.com/spreadsheets/d/14S-mSE72HbEBH5BBUdsAgclJ3CUBA3Vq2bTiY23tWTc/edit?gid=0#gid=0

# To add more mansions:
# 1. Add new tab into master search result, name it properly
# 2. Duplicate 1 Diff sheet from existing Diff sheets
# 3. Add new config below, use a new base search url, new result_tab
# 4. Add execution in main() with a custom filter

# Special: no price limit
keibai_domain = "https://xn--55q36pba3495a.com"
keibai_base_url = "https://xn--55q36pba3495a.com/auction/find?pid=13&pid=14&pid=12&pid=11&pid=8&pid=27&pid=28&grp=1&grp=2&sqmin=40&sqmax=60&wmax=10"
keibai_tab_index = 0
keibai_diff_sheet_name = 'Keibai Diff'

class Property(NamedTuple):
    name: str
    evaluate_price: float
    bid_starting_price: float
    deposit: float
    bid_period: str

    address: str
    station_access: str
    built_year: str
    area: str
    floor: str
    structure: str

    pdf_url: str
    url: str

# Mapping
def get_html(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.content, "html.parser")
    return soup

def url_from_item(item):
    link = item.find('a')
    return 'https://suumo.jp' + link['href']

def value_next_to_dt(col, title_str: str) -> str:
    target = col.find('dt', string=title_str)
    if not target:
        return None

    next_sib = target.find_next_sibling()
    if not next_sib:
        return None

    return next_sib.text

def extract_name(s):
    match = re.search(r'「(.*?)」', s)
    if match:
        return match.group(1)
    
    match = re.search(r'(\S*駅\S*)', s)
    return match.group(1) if match else s

def get_property(url):
    soup = get_html(url)

    try:
        col = soup.find('div', {'class': 'col-l bit'})

        name = col.find('h1').text
        name = extract_name(name) 

        evaluate_price = parse_price_float(value_next_to_dt(col, '売却基準価額'))
        deposit = parse_price_float(value_next_to_dt(col, '買受申出保証額'))
        bid_staring_price = parse_price_float(value_next_to_dt(col,'買受可能価額'))
        bid_period = value_next_to_dt(col, '入札期間')
        address = value_next_to_dt(col, '所在地')
        station_access = value_next_to_dt(col, '参考交通')
        built_year = value_next_to_dt(col, '築年月')
        match = re.search(r'\((.*?)\)', built_year)
        built_year = match.group(1) if match else built_year

        # Extract props structure (multiple items)
        start_tag = col.find('h2', string='物件詳細')
        end_tag = col.find('h2', string='売却スケジュール')
        props = []
        sibling = start_tag
        while sibling != end_tag:
            sibling = sibling.find_next_sibling()
            if sibling.name != 'dl':
                continue
            if sibling.find('dt',string='注意事項'):
                continue
            props.append(sibling)

        prop = [p for p in props if value_next_to_dt(p, '種別') in ['区分所有建物', '建物']][0]
        area = value_next_to_dt(prop, '専有面積 (登記)') or value_next_to_dt(prop, '床面積 (登記)')
        floor = value_next_to_dt(prop, '階') 
        structure = value_next_to_dt(prop, '構造 (登記)')
        

        pdf_url = col.find('a', title='物件資料PDFをダウンロード')['href']
        image_urls =[child.find('img') for child in col.find('div', {'class': 'pswp-gallery'}).findChildren()] 
        image_urls = [p for p in image_urls if p is not None]
        image_urls = ['https:' + p['src'] for p in image_urls]

        return Property(
            name=name,
            evaluate_price=evaluate_price,
            bid_starting_price=bid_staring_price,
            deposit=deposit,
            bid_period=bid_period,
            address=address,
            station_access=station_access,
            built_year=built_year,
            area=area,
            floor=floor,
            structure=structure,
            pdf_url=pdf_url,
            url=url,
        )
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        return 

# 1億480万円 -> 10480
# 1億4800万円 -> 14800
# 9500 -> 9500
def parse_price_float(price) -> float:
    no_unit = price.replace(',', '').split("円")[0]
    return float(no_unit) / 10000

def get_urls(base_url):
    soup = get_html(base_url)
    items = soup.findAll('a', {'class': 'article__a bit'})
    urls = [keibai_domain + i['href'] for i in items]

    return urls 

def multiply_images(image_urls):
    return [f'=IMAGE("{url}")' for url in image_urls]

def property_to_array(property):
    return [
        property.name, 
        property.evaluate_price, 
        property.bid_starting_price, 
        property.deposit, 
        property.bid_period, 
        property.address, 
        property.station_access, 
        property.built_year, 
        property.area,
        property.floor,
        property.structure,
        property.pdf_url,
        property.url,
    ]

def property_to_array_with_time(property):
    return [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        property.name, 
        property.evaluate_price, 
        property.bid_starting_price, 
        property.deposit, 
        property.bid_period, 
        property.address, 
        property.station_access, 
        property.built_year, 
        property.area,
        property.floor,
        property.structure,
        property.pdf_url,
        property.url,
    ]

def load_property_from_array(row):
    try: 
        return Property(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
            row[10],
            row[11],
            row[12],
        )
    except:
        return

def load_properties_from_cells(worksheet):
    cells = worksheet.get_all_values(include_tailing_empty_rows=False, include_tailing_empty=False, returnas='matrix')
    cells.pop(0) # Ignore filters row
    loaded = [load_property_from_array(row) for row in cells] 
    return [p for p in loaded if p is not None]

def unique_key(property):
    return property.url

def write_to_gsheets(searched_properties, result_tab, diff_sheet_name):
    gc = pygsheets.authorize(service_file=gsheet_policy_json)
    result_tab = gc.open(result_sheet_name)[result_tab]

    # Diff by direct_url
    loaded_properties = load_properties_from_cells(result_tab)
    appending_properties = list(filter(lambda x: x.url != "", searched_properties))
    new_arrivial = [x for x in appending_properties if unique_key(x) not in map(unique_key, loaded_properties)]
    removed = [x for x in loaded_properties if unique_key(x) not in map(unique_key, appending_properties)]
    print("New Arrival: " + str(len(new_arrivial)))
    print("Removed: " + str(len(removed)))

    # Save diffs
    added_tab = gc.open(diff_sheet_name)[0]
    removed_tab = gc.open(diff_sheet_name)[1]
    if len(new_arrivial) > 0:
        added_tab.insert_rows(0, number=1, values="")
        added_tab.insert_rows(0, number=len(new_arrivial), values=list(map(property_to_array_with_time, new_arrivial)))
    if len(removed) > 0:
        removed_tab.insert_rows(0, number=1, values="")
        removed_tab.insert_rows(0, number=len(removed), values=list(map(property_to_array_with_time, removed)))

    # Save latest result
    rows = list(map(property_to_array, searched_properties))
    result_tab.clear('A2')
    if len(rows) > 0:
        result_tab.delete_rows(2, number=len(rows))
        result_tab.insert_rows(1, number=len(rows), values=rows)

def save_from_url(base_url, written_tab_index, diff_sheet_name, custom_filter):
    urls = get_urls(base_url)

    properties = list(map(get_property, urls))
    properties = [p for p in properties if p is not None]
    properties = list(filter(custom_filter, properties))
    properties = sorted(properties, key=lambda x: float(x.evaluate_price))
    print("{} result".format(len(properties)))

    write_to_gsheets(properties, written_tab_index, diff_sheet_name)

def main():
    print(datetime.now())
    print('----------')
    print("keibai")

    # Testing
    save_from_url(
        keibai_base_url, 
        keibai_tab_index, 
        keibai_diff_sheet_name, 
        lambda x: x
    )
    print('----------')
    print(datetime.now())
    print('------------------------------')

if __name__ == "__main__":
    main()
