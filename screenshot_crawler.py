import asyncio
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
import os
import re
import sys
import json
import argparse
from datetime import datetime
import shutil

# Carrega as configurações do arquivo config.json
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("Erro: Arquivo config.json não encontrado. Crie um para configurar as resoluções.")
    sys.exit(1)

RESOLUTIONS = CONFIG.get("resolutions", [])
MAX_PAGES_DEFAULT = CONFIG.get("max_pages", 50)
DELAY_BETWEEN_PAGES = CONFIG.get("delay_between_pages_seconds", 2)
DELAY_BETWEEN_RESOLUTIONS = CONFIG.get("delay_between_resolutions_ms", 1000)
MAX_CONCURRENT_PAGES = CONFIG.get("max_concurrent_pages", 3)

def sanitize_filename(url):
    """Gera um nome de arquivo seguro baseado na URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "index"
    # Substitui caracteres não alfanuméricos por underline
    return re.sub(r'[^a-zA-Z0-9_]', '_', path)

async def worker(worker_id, browser, base_domain, queue, visited, max_pages):
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        while True:
            try:
                # O timeout evita que a tarefa trave infinitamente se a fila esvaziar
                url = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                break
            except asyncio.CancelledError:
                break
                
            # Preserva rotas de SPA (ex: #/about) mas remove âncoras comuns (ex: #section1)
            url_clean = url
            if '#' in url:
                base, hash_part = url.split('#', 1)
                if hash_part.startswith('/') or hash_part.startswith('!'):
                    url_clean = url
                else:
                    url_clean = base
            
            if url_clean in visited or len(visited) >= max_pages:
                queue.task_done()
                if len(visited) >= max_pages:
                    break
                continue
                
            visited.add(url_clean)
            print(f"\n[Worker {worker_id} | {len(visited)}/{max_pages}] Visitando: {url_clean}")
            
            try:
                await page.goto(url_clean, wait_until="networkidle", timeout=30000)
                page_name = sanitize_filename(url_clean)
                page_dir = os.path.join("screenshots", page_name)
                os.makedirs(page_dir, exist_ok=True)
                
                for res in RESOLUTIONS:
                    await page.set_viewport_size({"width": res["width"], "height": res["height"]})
                    await page.wait_for_timeout(DELAY_BETWEEN_RESOLUTIONS)
                    
                    filepath = os.path.join(page_dir, f"{res['name']}.png")
                    await page.screenshot(path=filepath, full_page=True)
                    print(f"  [Worker {worker_id}] -> Screenshot salva: {filepath}")
                
                links = await page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")
                
                for link in links:
                    full_link = urljoin(url_clean, link).split('#')[0]
                    if urlparse(full_link).netloc == base_domain and full_link not in visited:
                        if not any(full_link.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.zip', '.mp4', '.gif']):
                            await queue.put(full_link)
                            
            except Exception as e:
                print(f"  [Worker {worker_id}] Erro ao acessar {url_clean}: {e}")
            
            queue.task_done()
            
            if len(visited) < max_pages and not queue.empty():
                print(f"  [Worker {worker_id}] -> Aguardando {DELAY_BETWEEN_PAGES} segundo(s)...")
                await asyncio.sleep(DELAY_BETWEEN_PAGES)
            
            if len(visited) >= max_pages:
                break
    finally:
        await context.close()

async def crawl_and_screenshot(start_url, max_pages=MAX_PAGES_DEFAULT):
    visited = set()
    queue = asyncio.Queue()
    await queue.put(start_url)
    base_domain = urlparse(start_url).netloc
    
    # Backup da pasta screenshots anterior, se existir
    if os.path.exists("screenshots"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"screenshots_backup_{timestamp}"
        try:
            shutil.move("screenshots", backup_dir)
            print(f"Backup criado: a pasta anterior foi renomeada para '{backup_dir}'\n")
        except Exception as e:
            print(f"Aviso: Não foi possível fazer o backup da pasta screenshots: {e}")
            
    os.makedirs("screenshots", exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        workers = []
        for i in range(MAX_CONCURRENT_PAGES):
            task = asyncio.create_task(worker(i+1, browser, base_domain, queue, visited, max_pages))
            workers.append(task)
            
        # Monitora a fila para saber quando terminamos ou batemos o limite de páginas
        monitor_task = asyncio.create_task(queue.join())
        while not monitor_task.done():
            done, pending = await asyncio.wait([monitor_task], timeout=1.0)
            if len(visited) >= max_pages:
                break
                
        # Cancela os workers que ainda estão esperando por itens
        for w in workers:
            if not w.done():
                w.cancel()
        
        # Espera os workers finalizarem e fecharem os contextos do navegador
        await asyncio.gather(*workers, return_exceptions=True)
        await browser.close()
        
        print(f"\nFim da varredura. Total de páginas processadas: {len(visited)}")
        print("As imagens estão salvas na pasta 'screenshots/'.")

def interactive_mode():
    print("="*50)
    print("Bem-vindo ao Screem Printer Crawler!")
    print("="*50)
    target_url = input("Digite a URL do site que deseja varrer (ex: https://exemplo.com): ").strip()
    
    if not target_url:
        print("URL inválida.")
        sys.exit(1)
        
    pages_input = input(f"Máximo de páginas a varrer (padrão: {MAX_PAGES_DEFAULT}): ").strip()
    max_pages = int(pages_input) if pages_input.isdigit() else MAX_PAGES_DEFAULT
    
    return target_url, max_pages

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script para varrer um site e tirar screenshots em múltiplas resoluções.")
    parser.add_argument("-u", "--url", type=str, help="URL do site para varrer")
    parser.add_argument("-m", "--max-pages", type=int, help="Número máximo de páginas para visitar")
    parser.add_argument("-i", "--interactive", action="store_true", help="Inicia o modo interativo")
    
    args = parser.parse_args()
    
    # Se não passou nada ou pediu interativo, abre o modo interativo
    if args.interactive or len(sys.argv) == 1:
        target_url, max_pages = interactive_mode()
    else:
        if not args.url:
            parser.error("A URL é obrigatória no modo CLI. Use -u <URL> ou execute sem argumentos para o modo interativo.")
        target_url = args.url
        max_pages = args.max_pages if args.max_pages is not None else MAX_PAGES_DEFAULT
    
    # Verifica se a URL tem http/https
    if not target_url.startswith('http'):
        target_url = 'https://' + target_url

    try:
        asyncio.run(crawl_and_screenshot(target_url, max_pages))
    except KeyboardInterrupt:
        print("\nVarredura interrompida pelo usuário.")
