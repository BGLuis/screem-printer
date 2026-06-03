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
import copy
import hashlib

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

async def worker(worker_id, browser, base_domain, queue, visited, max_pages, active_resolutions, storage_state_path, mode, visited_layouts):
    if storage_state_path and os.path.exists(storage_state_path):
        context = await browser.new_context(storage_state=storage_state_path)
    else:
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
                
                # Modo 2: Auto-inteligente (Verifica o Hash Estrutural do DOM para pular layouts repetidos)
                skip_screenshots = False
                if mode == 2:
                    dom_structure = await page.evaluate('''() => {
                        function walk(node) {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                let res = node.tagName;
                                for (let child of node.childNodes) {
                                    res += walk(child);
                                }
                                return res;
                            }
                            return '';
                        }
                        return walk(document.body);
                    }''')
                    layout_hash = hashlib.md5(dom_structure.encode('utf-8')).hexdigest()
                    
                    if layout_hash in visited_layouts:
                        print(f"  [Worker {worker_id}] -> Layout repetido detectado. Pulando capturas de tela, mas buscando links.")
                        skip_screenshots = True
                    else:
                        visited_layouts.add(layout_hash)

                if not skip_screenshots:
                    page_name = sanitize_filename(url_clean)
                    page_dir = os.path.join("screenshots", page_name)
                    os.makedirs(page_dir, exist_ok=True)
                    
                    for res in active_resolutions:
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

async def guided_exploration(start_url, active_resolutions, login_required):
    print("\n" + "="*50)
    print("INICIANDO EXPLORAÇÃO GUIADA PELO USUÁRIO")
    print("="*50)
    print("- Um navegador será aberto.")
    if login_required:
        print("- Faça seu login normalmente.")
    print("- Navegue pelo site, abra modais, menus laterais, etc.")
    print("- Quando quiser tirar print da TELA ATUAL em todas as resoluções:")
    print("   -> Clique no botão verde no canto inferior direito")
    print("   -> OU pressione Ctrl + Espaço")
    print("- O script irá pausar você, capturar tudo e deixar você continuar.")
    print("- Feche o navegador quando terminar.")
    print("="*50 + "\n")
    
    os.makedirs("screenshots", exist_ok=True)
    capture_count = [1]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_capture(source):
            page_obj = source['page']
            current_url = page_obj.url
            print(f"\n[!] Iniciando captura do estado atual... (URL: {current_url})")
            
            try:
                original_size = page_obj.viewport_size
                if not original_size:
                    original_size = {"width": 1280, "height": 720}
                    
                page_name = f"guiada_{capture_count[0]:03d}_" + sanitize_filename(current_url)
                page_dir = os.path.join("screenshots", page_name)
                os.makedirs(page_dir, exist_ok=True)
                capture_count[0] += 1
                
                for res in active_resolutions:
                    await page_obj.set_viewport_size({"width": res["width"], "height": res["height"]})
                    await page_obj.wait_for_timeout(DELAY_BETWEEN_RESOLUTIONS)
                    filepath = os.path.join(page_dir, f"{res['name']}.png")
                    await page_obj.screenshot(path=filepath, full_page=True)
                    print(f"  -> Salvo: {filepath}")
                    
                await page_obj.set_viewport_size(original_size)
                print("[!] Capturas concluídas. Pode continuar explorando!")
            except Exception as e:
                print(f"[Erro] Falha ao capturar a tela: {e}")

        await context.expose_binding("triggerCapture", lambda source: asyncio.create_task(handle_capture(source)))

        init_script = """
        if (!window.captureInjected) {
            window.captureInjected = true;
            
            document.addEventListener('keydown', e => {
                if (e.ctrlKey && e.code === 'Space') {
                    e.preventDefault();
                    window.triggerCapture();
                }
            });
            
            // Injeta o botão apenas após o carregamento da página para garantir que ele apareça
            window.addEventListener('load', () => {
                if (document.getElementById('screem-printer-btn')) return;
                const btn = document.createElement('button');
                btn.id = 'screem-printer-btn';
                btn.innerHTML = '📸 Capturar Múltiplas Telas (Ctrl+Espaço)';
                btn.style.cssText = 'position:fixed; bottom:20px; right:20px; z-index:9999999; padding:15px; background:#4CAF50; color:white; border:none; border-radius:8px; font-weight:bold; cursor:pointer; box-shadow: 0 4px 6px rgba(0,0,0,0.3);';
                btn.onclick = () => window.triggerCapture();
                document.body.appendChild(btn);
            });
        }
        """
        await context.add_init_script(init_script)
        
        try:
            await page.goto(start_url)
            # Espera indefinidamente até que a página ou o contexto seja fechado
            await page.wait_for_event("close", timeout=0)
        except Exception as e:
            if "Target closed" not in str(e) and "browser has been closed" not in str(e):
                print(f"\nEncerrando exploração guiada. Motivo: {e}")
            else:
                print("\nNavegador fechado. Encerrando exploração guiada.")
        finally:
            if browser.is_connected():
                await browser.close()
            print("As imagens estão salvas na pasta 'screenshots/'.")

async def crawl_and_screenshot(start_url, max_pages=MAX_PAGES_DEFAULT, active_resolutions=None, login_required=False, mode=1):
    if active_resolutions is None:
        active_resolutions = RESOLUTIONS

    # Se for modo 3 (Guiado), a lógica é totalmente diferente
    if mode == 3:
        await guided_exploration(start_url, active_resolutions, login_required)
        return

    visited = set()
    visited_layouts = set() # Para o modo 2 (Auto-inteligente)
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
        storage_state_path = "login_state.json" if login_required else None
        
        if login_required:
            print("\n" + "="*50)
            print("LOGIN MANUAL NECESSÁRIO")
            print("="*50)
            print("Um navegador será aberto. Faça o login e resolva captchas se necessário.")
            print("NÃO feche o navegador.")
            login_browser = await p.chromium.launch(headless=False)
            login_context = await login_browser.new_context()
            login_page = await login_context.new_page()
            await login_page.goto(start_url)
            
            await asyncio.get_event_loop().run_in_executor(None, input, "\n>>> APÓS CONCLUIR O LOGIN, PRESSIONE [ENTER] AQUI PARA INICIAR A VARREDURA <<<")
            
            await login_context.storage_state(path=storage_state_path)
            await login_browser.close()
            print("Estado de login salvo. Iniciando varredura em modo invisível (headless)...")

        browser = await p.chromium.launch(headless=True)
        
        workers = []
        for i in range(MAX_CONCURRENT_PAGES):
            task = asyncio.create_task(worker(i+1, browser, base_domain, queue, visited, max_pages, active_resolutions, storage_state_path, mode, visited_layouts))
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
        
        if storage_state_path and os.path.exists(storage_state_path):
            try:
                os.remove(storage_state_path)
            except:
                pass
        
        print(f"\nFim da varredura automática. Total de páginas processadas: {len(visited)}")
        print("As imagens estão salvas na pasta 'screenshots/'.")

def menu_resolutions(active_resolutions):
    all_resolutions = CONFIG.get("resolutions", [])
    active_names = {r["name"] for r in active_resolutions}
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("="*50)
        print("Configurar Resoluções")
        print("="*50)
        
        for i, res in enumerate(all_resolutions):
            status = "[X]" if res["name"] in active_names else "[ ]"
            print(f"[{i+1:2d}] {status} {res['name']} ({res['width']}x{res['height']})")
            
        print("-" * 50)
        print("[T] Alternar todas")
        print("[V] Voltar")
        
        choice = input("\nDigite o número para alternar, T para todas ou V para voltar: ").strip().upper()
        
        if choice == 'V':
            break
        elif choice == 'T':
            if len(active_names) == len(all_resolutions):
                active_names.clear()
            else:
                active_names = {r["name"] for r in all_resolutions}
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_resolutions):
                res_name = all_resolutions[idx]["name"]
                if res_name in active_names:
                    active_names.remove(res_name)
                else:
                    active_names.add(res_name)
                    
    return [r for r in all_resolutions if r["name"] in active_names]

def interactive_menu():
    active_resolutions = copy.deepcopy(CONFIG.get("resolutions", []))
    target_url = ""
    max_pages = MAX_PAGES_DEFAULT
    login_required = False
    mode = 1 # 1=Padrao, 2=Inteligente(Hash), 3=Guiado
    
    modes_desc = {
        1: "Automático Padrão (Varre links indiscriminadamente)",
        2: "Automático Inteligente (Evita páginas com o mesmo layout)",
        3: "Exploração Guiada (Você navega, abre modais e decide onde tirar prints)"
    }
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("="*50)
        print("Screem Printer Crawler - Menu Interativo")
        print("="*50)
        print(f"URL Alvo: {target_url if target_url else 'Não definida'}")
        print(f"Máximo de páginas: {max_pages}")
        print(f"Login Manual: {'Ativado' if login_required else 'Desativado'}")
        print(f"Modo de Exploração: {modes_desc[mode]}")
        print(f"Resoluções ativas: {len(active_resolutions)} de {len(CONFIG.get('resolutions', []))}")
        print("-" * 50)
        print("[1] Definir URL alvo")
        print("[2] Configurar máximo de páginas")
        print("[3] Configurar resoluções")
        print("[4] Alternar necessidade de Login Manual")
        print("[5] Alternar Modo de Exploração")
        print("[6] Iniciar Varredura")
        print("[0] Sair")
        
        choice = input("\nEscolha uma opção: ").strip()
        
        if choice == '1':
            url = input("Digite a URL alvo (ex: https://exemplo.com): ").strip()
            if url:
                target_url = url
        elif choice == '2':
            pages = input(f"Máximo de páginas (padrão {MAX_PAGES_DEFAULT}): ").strip()
            if pages.isdigit():
                max_pages = int(pages)
        elif choice == '3':
            active_resolutions = menu_resolutions(active_resolutions)
        elif choice == '4':
            login_required = not login_required
            print(f"\nLogin Manual {'ativado' if login_required else 'desativado'}.")
            input("Pressione ENTER para continuar...")
        elif choice == '5':
            print("\nModos disponíveis:")
            for k, v in modes_desc.items():
                print(f"[{k}] {v}")
            m_choice = input("Escolha o modo (1, 2 ou 3): ").strip()
            if m_choice in ['1', '2', '3']:
                mode = int(m_choice)
                if mode == 3 and not login_required:
                    # O modo guiado naturalmente já é manual, mas não força a criar o state.json
                    # Não há problema
                    pass
        elif choice == '6':
            if not target_url:
                print("\nPor favor, defina a URL alvo primeiro (Opção 1).")
                input("Pressione ENTER para continuar...")
                continue
            if not active_resolutions:
                print("\nPelo menos uma resolução deve estar ativa.")
                input("Pressione ENTER para continuar...")
                continue
            break
        elif choice == '0':
            sys.exit(0)
            
    return target_url, max_pages, active_resolutions, login_required, mode

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script para varrer um site e tirar screenshots em múltiplas resoluções.")
    parser.add_argument("-u", "--url", type=str, help="URL do site para varrer")
    parser.add_argument("-m", "--max-pages", type=int, help="Número máximo de páginas para visitar")
    parser.add_argument("-l", "--login", action="store_true", help="Ativa o modo de login manual antes da varredura")
    parser.add_argument("-i", "--interactive", action="store_true", help="Inicia o modo interativo")
    parser.add_argument("--mode", type=int, choices=[1, 2, 3], default=1, help="Modo de exploração: 1=Padrão, 2=Inteligente (Hash), 3=Guiado pelo Usuário")
    
    args = parser.parse_args()
    
    if args.interactive or len(sys.argv) == 1:
        target_url, max_pages, active_resolutions, login_required, mode = interactive_menu()
    else:
        if not args.url:
            parser.error("A URL é obrigatória no modo CLI. Use -u <URL> ou execute sem argumentos para o modo interativo.")
        target_url = args.url
        max_pages = args.max_pages if args.max_pages is not None else MAX_PAGES_DEFAULT
        active_resolutions = RESOLUTIONS
        login_required = args.login
        mode = args.mode
    
    if not target_url.startswith('http'):
        target_url = 'https://' + target_url

    try:
        asyncio.run(crawl_and_screenshot(target_url, max_pages, active_resolutions, login_required, mode))
    except KeyboardInterrupt:
        print("\nVarredura interrompida pelo usuário.")
