"""Check the generated technical reference online and offline; never start Core."""
import argparse,functools,threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect
from build_manual import page,validate
ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--screenshots',type=Path)
    output=parser.parse_args().screenshots
    if output:output.mkdir(parents=True,exist_ok=True)
    validate(page())
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch();tab=browser.new_page(viewport={'width':1440,'height':960})
            errors=[];api=[]
            tab.on('pageerror',lambda e:errors.append(str(e)))
            tab.on('request',lambda r:api.append(r.url) if '/api/' in r.url else None)
            tab.goto(f'http://127.0.0.1:{server.server_port}/index.html')
            expect(tab.locator('h1')).to_contain_text('Техническая справка')
            tab.locator('#docSearch').fill('maskAsset');expect(tab.locator('#docSearchResults a').first).to_be_visible()
            tab.locator('#docSearch').press('Escape');expect(tab.locator('#docSearchResults')).to_be_hidden()
            before=tab.locator('body').get_attribute('data-doc-theme');tab.locator('#sidebarThemeSlot button').click()
            assert tab.locator('body').get_attribute('data-doc-theme')!=before
            if output:tab.screenshot(path=str(output/'reference-desktop.png'))
            tab.set_viewport_size({'width':390,'height':844});assert tab.evaluate('document.documentElement.scrollWidth')<=392
            if output:tab.screenshot(path=str(output/'reference-mobile.png'))
            tab.goto((ROOT/'index.html').as_uri());tab.locator('#docSearch').fill('revision');expect(tab.locator('#docSearchResults a').first).to_be_visible()
            assert not errors,errors
            assert not api,'Reference must not access application data: '+str(api)
            browser.close()
    finally:server.shutdown();server.server_close()
    print('Reference: online/offline search, theme, mobile width and no API access passed.')
if __name__=='__main__':main()
