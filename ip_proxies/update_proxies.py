import requests as r
from bs4 import BeautifulSoup


def update():
    resp = r.get("https://free-proxy-list.net/")
    soup = BeautifulSoup(resp.content, 'html.parser')

    with open('ip_proxies/list.txt', 'w') as f:
        for row in soup.find(id="proxylisttable").find_all('tr'):
            values = [item.text.strip() for item in row.find_all('td')]
            if len(values) > 1:
                f.write(f'http://{values[0]}:{values[1]}\n')


if __name__ == '__main__':
    update()