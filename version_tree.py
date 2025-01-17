import openpyxl
import logging
import time
import pandas as pd
import sys
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Definir um excepthook para capturar exceções não tratadas
def excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt): 
        # Permite que o KeyboardInterrupt seja tratado normalmente
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error(f"Exceção não capturada: {exc_value}")

sys.excepthook = excepthook

class DataHandler:
    def __init__(self, file_path, sheet_name):
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.df = pd.read_excel(file_path, sheet_name=sheet_name)
        self.df.columns = [col.upper().strip() for col in self.df.columns]
        if 'CONFIRMACOES' not in self.df.columns:
            self.df['CONFIRMACOES'] = ''
        if 'ERRO' not in self.df.columns:
            self.df['ERRO'] = ''
        if 'QT_CONFIRMADA' not in self.df.columns:
            self.df['QT_CONFIRMADA'] = ''  # Inicializa com valores vazios ou zero

    def get_value(self, row_index, column_name):
        """Obtém o valor de uma coluna específica em uma linha específica."""
        try:
            value = self.df.at[row_index, column_name.upper()]
            if pd.isnull(value):
                return ""
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value).strip()
        except KeyError:
            logging.error(f"A coluna '{column_name}' não foi encontrada.")
            return ""

    def update_value(self, row_index, column_name, value):
        """Atualiza o valor de uma célula específica."""
        try:
            self.df.at[row_index, column_name.upper()] = value
            excel_line_number = row_index + 2  # Ajuste para corresponder à linha no Excel
            logging.info(f"Valor atualizado na linha {excel_line_number}, coluna '{column_name}': {value}")
        except KeyError:
            logging.error(f"A coluna '{column_name}' não foi encontrada ao tentar atualizar o valor.")

    def save(self):
        """Salva o DataFrame de volta ao arquivo Excel."""
        try:
            # Salva no mesmo arquivo para evitar problemas
            self.df.to_excel(self.file_path, sheet_name=self.sheet_name, index=False)
            logging.info(f"Alterações salvas no arquivo Excel com sucesso: {self.file_path}")
        except Exception as e:
            error_message = getattr(e, 'message', str(e))
            logging.error(f"Erro ao salvar o arquivo Excel: {error_message}")

class BaseAutomation:
    def __init__(self):
        """Configurações gerais do WebDriver."""
        self.options = Options()
        self.options.add_argument("--start-maximized")
        self.driver = webdriver.Chrome(options=self.options)

    def wait_for_stability(self, timeout=10, check_interval=1):
        """Espera pela estabilidade da altura da página."""
        old_height = self.driver.execute_script("return document.body.scrollHeight;")
        for _ in range(timeout):
            time.sleep(check_interval)
            new_height = self.driver.execute_script("return document.body.scrollHeight;")
            if new_height == old_height:
                break
            old_height = new_height

    def safe_click(self, by_locator):
        """Tenta clicar no elemento várias vezes se for interceptado."""
        for _ in range(3):
            try:
                element = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(by_locator))
                element.click()
                logging.info(f"Elemento clicado com sucesso: {by_locator}")
                return
            except Exception as e:
                error_message = getattr(e, 'msg', str(e))
                logging.warning(f"Erro ao clicar no elemento: {error_message}")
                time.sleep(1)
        raise Exception("Não foi possível clicar no elemento após várias tentativas.")

    def acessar_com_reattempt(self, by_locator, attempts=3):
        """Tenta acessar um elemento várias vezes."""
        for attempt in range(attempts):
            try:
                element = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(by_locator))
                logging.info(f"Elemento encontrado: {by_locator}")
                return element
            except TimeoutException:
                logging.warning(f"Tentativa {attempt + 1} falhou. Tentando novamente...")
                time.sleep(1)
        raise Exception(f"Não foi possível acessar o elemento após {attempts} tentativas.")

    def scroll_and_click(self, element):
        """Rola a página para o elemento e clica nele."""
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(2)
        element.click()

class VerificationIPASGO(BaseAutomation):
    def __init__(self, data_handler):
        super().__init__()
        self.data_handler = data_handler
        self.row_index = 0  # Inicie com o índice desejado

        # Caminho para o arquivo txt onde as confirmações serão salvas
        self.txt_file_path = r"C:\Users\SUPERVISÃO ADM\Desktop\RPA_verificação_ipasgo\salvamento_datas_confirmação.txt"

        # Obter as credenciais das variáveis de ambiente
        self.username = os.environ.get('IPASGO_USERNAME')
        self.password = os.environ.get('IPASGO_PASSWORD')
        if not self.username or not self.password:
            raise Exception("As credenciais não foram encontradas nas variáveis de ambiente.")

    def acessar_portal_ipasgo(self):
        """Executa o fluxo de login no portal IPASGO."""
        try:
            self.driver.get("https://portalos.ipasgo.go.gov.br/Portal_Dominio/PrestadorLogin.aspx")
            self.wait_for_stability(timeout=10)

            matricula_input = self.acessar_com_reattempt((By.ID, "SilkUIFramework_wt13_block_wtUsername_wtUserNameInput2"))
            matricula_input.send_keys(self.username)

            senha_input = self.acessar_com_reattempt((By.ID, "SilkUIFramework_wt13_block_wtPassword_wtPasswordInput"))
            senha_input.send_keys(self.password)

            self.safe_click((By.ID, "SilkUIFramework_wt13_block_wtAction_wtLoginButton"))

            # Verificar se o alerta está dentro de um iframe (opcional)
            try:
                # Localiza todos os iframes na página
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    self.driver.switch_to.frame(iframe)
                    try:
                        fechar_alerta = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//a[contains(@id, 'wt15')]/span[contains(@class, 'fa-close')]"))
                        )
                        fechar_alerta.click()
                        logging.info("Alerta detectado e fechado dentro de um iframe.")
                        self.driver.switch_to.default_content()
                        self.wait_for_stability(timeout=5)
                        break  # Sai do loop após fechar o alerta
                    except TimeoutException:
                        self.driver.switch_to.default_content()
                        continue
            except Exception as e:
                pass

            self.wait_for_stability(timeout=10)

            link_portal_webplan = self.acessar_com_reattempt(
                (By.XPATH, "//*[@id='IpasgoTheme_wt16_block_wtMainContent_wtSistemas_ctl08_SilkUIFramework_wt36_block_wtActions_wtModulos_SilkUIFramework_wt9_block_wtContent_wtModuloPortalTable_ctl04_wt2']/span")
            )
            self.scroll_and_click(link_portal_webplan)

            WebDriverWait(self.driver, 20).until(EC.number_of_windows_to_be(2))
            self.driver.switch_to.window(self.driver.window_handles[1])

            self.acessar_com_reattempt((By.ID, "menuPrincipal"))

            time.sleep(4)
            logging.info("Login realizado com sucesso.")

            # Chamar localizar_procedimentos apenas uma vez, como parte do login
            self.localizar_procedimentos()

        except Exception as e:
            error_message = getattr(e, 'msg', str(e))
            logging.error(f"Erro ao acessar o portal IPASGO: {error_message}")
            # Atualizar a coluna 'ERRO' no Excel
            self.data_handler.update_value(self.row_index, 'ERRO', error_message)
            self.data_handler.save()
            raise  # Repassa a exceção para ser tratada no nível superior

    def localizar_procedimentos(self):
        """Função para localizar e clicar no elemento 'localizar-procedimentos'."""
        try:
            logging.info("Localizando o menu de procedimentos.")
            procedimentos_button = self.acessar_com_reattempt((By.CSS_SELECTOR, ".localizar-procedimentos-icon"))
            self.scroll_and_click(procedimentos_button)
            time.sleep(5)

            # Verifica se o alerta aparece e lida com ele se necessário
            self.close_alert_if_present()

        except Exception as e:
            error_message = getattr(e, 'msg', str(e))
            logging.error(f"Erro ao acessar o menu de procedimentos: {error_message}")
            # Atualizar a coluna 'ERRO' no Excel
            self.data_handler.update_value(self.row_index, 'ERRO', error_message)
            self.data_handler.save()
            raise

    def close_alert_if_present(self):
        """Fecha o alerta se estiver presente."""
        try:
            logging.info("Verificando se o alerta está presente.")
            alerta = WebDriverWait(self.driver, 2).until(EC.visibility_of_element_located((By.XPATH, '//*[@id="button-1"]')))
            alerta.click()
            logging.info("Alerta fechado com sucesso.")
        except TimeoutException:
            logging.info("Nenhum alerta encontrado, continuando o processo.")



    def executar_fluxo_para_linha(self):
        """Executa o fluxo de interações para a linha atual, com a lógica do guia repetido."""
        try:
            # Obter o número da guia desta linha
            numero_guia = self.data_handler.get_value(self.row_index, 'GUIA_COD')

            # Verifica se o número da guia desta linha é o mesmo da linha anterior
            if numero_guia == self.last_guia:
                # Se for o mesmo, não chama Guia_operadora novamente
                logging.info(f"Guia {numero_guia} já foi localizada anteriormente. Pulando 'Guia_operadora()'.")
            else:
                # Se for diferente, chamamos Guia_operadora para filtrar a nova guia
                self.Guia_operadora()

            # Fluxo normal de confirmação
            self.abrir_confirmar_procedimentos()
            self.Clicar_confirmar_procedimento()
            self.fechar_alerta_notificacao()

            # Após concluir a confirmação (fechar_alerta_notificacao), atualizamos o last_guia
            self.last_guia = numero_guia

            # Agora executa o scroll para preparar o próximo número de guia
            self.scroll_into_view()

        except Exception as e:
            error_message = getattr(e, 'msg', str(e))
            logging.error(f"Erro ao executar o fluxo na linha {self.row_index + 2}: {error_message}")
            # Atualizar a coluna 'ERRO' no Excel
            self.data_handler.update_value(self.row_index, 'ERRO', error_message)
            self.data_handler.save()



    def Guia_operadora(self):
        """Função para inserir o número da guia para localizar procedimento usando dados da planilha."""
        try:
            numero_guia = self.data_handler.get_value(self.row_index, 'GUIA_COD')
            logging.info("Localizando o campo de número da guia.")

            guia_input = self.acessar_com_reattempt((By.CSS_SELECTOR, 'div.input-group > input.form-control.small'))
            guia_input.clear()
            guia_input.send_keys(str(numero_guia))
            logging.info(f"Número da guia preenchido com sucesso: {numero_guia}")

            search_button = self.acessar_com_reattempt((By.XPATH, "//div[contains(@class, 'input-group')]//span[contains(@class, 'fa-search') and contains(@class, 'pointer')]"))
            search_button.click()

            time.sleep(2)

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        except Exception as e:
            error_message = getattr(e, 'msg', str(e))
            logging.error(f"Erro ao preencher o número da guia: {error_message}")
            # Não atualizar a coluna 'ERRO' no Excel

    def abrir_confirmar_procedimentos(self):
        """Função para confirmar procedimentos executados."""
        try:
            logging.info("Iniciando o processo de confirmação dos procedimentos.")
            confirmar_button = self.acessar_com_reattempt((By.XPATH, '//*[@id="localizarprocedimentos"]/div[2]/div/div[2]/div/div[2]/div[1]/div/div/div/div[2]/div[2]/div/div[1]/div/div[1]/div[2]/div/i[2]'))
            confirmar_button.click()
            logging.info("Botão de confirmação clicado com sucesso.")
            time.sleep(2)
            self.capturar_data_procedimentos()
        except Exception as e:
            error_message = getattr(e, 'msg', str(e))
            logging.error(f"Erro ao tentar confirmar os procedimentos: {error_message}")
            # Não atualizar a coluna 'ERRO' no Excel

    def capturar_data_procedimentos(self):
        """Captura os textos de confirmação dos procedimentos exibidos no modal e salva em uma lista."""
        try:
            logging.info("Iniciando captura de confirmações dos procedimentos.")

            # Aguardando a presença do modal
            modal = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.ID, 'confirmar-procedimentos-modal'))
            )
            logging.info("Modal de confirmação está visível.")

            # Localiza todos os itens de confirmação dentro do modal
            confirmacao_itens = modal.find_elements(By.XPATH, '//*[@id="confirmar-procedimentos-modal"]/div/div/div[2]/div[2]/div/div[2]/div/div')

            self.confirmation_status_list = []  # Inicializa a lista para armazenar os status

            for idx, item in enumerate(confirmacao_itens):
                # Captura o texto do elemento de confirmação
                texto_confirmacao = item.find_element(By.XPATH, './/span[starts-with(@data-bind, "text: IsConfirmado()")]').text.strip()
                self.confirmation_status_list.append(texto_confirmacao)
                logging.info(f"Confirmação capturada na posição {idx + 1}: {texto_confirmacao}")

            # Atualiza a coluna 'CONFIRMACOES' no Excel
            confirmacoes_texto = "; ".join(self.confirmation_status_list)
            self.data_handler.update_value(self.row_index, 'CONFIRMACOES', confirmacoes_texto)

            # Contar o número de procedimentos confirmados
            qt_confirmada = sum(1 for status in self.confirmation_status_list if status.startswith('Confirmado'))
            # Atualizar a coluna 'QT_CONFIRMADA' no Excel
            self.data_handler.update_value(self.row_index, 'QT_CONFIRMADA', qt_confirmada)
            logging.info(f"Número de procedimentos confirmados: {qt_confirmada}")

            self.data_handler.save()

            # Escreve as confirmações no arquivo .txt
            with open(self.txt_file_path, 'a', encoding='utf-8') as f:
                excel_line_number = self.row_index + 2
                f.write(f"Linha {excel_line_number}: {confirmacoes_texto}\n")

            logging.info(f"Confirmações capturadas e salvas em '{self.txt_file_path}'.")

            # Chama a função para processar os procedimentos não confirmados

        except Exception as e:
            logging.error(f"Erro ao capturar confirmações: {e}")



    def Clicar_confirmar_procedimento(self):
        """
        Verifica os elementos na lista de confirmações capturada na função anterior.
        Processa apenas a primeira linha com 'Não confirmado'.
        """
        try:
            logging.info("Iniciando processamento do primeiro procedimento não confirmado.")

            # Verificar se a lista de status foi preenchida
            if not hasattr(self, 'confirmation_status_list') or not self.confirmation_status_list:
                return

            # Percorre cada status na lista
            for idx, status_text in enumerate(self.confirmation_status_list):
                position = idx + 1  # As posições começam em 1

                logging.info(f"Status do procedimento na posição {position}: '{status_text}'")

                if status_text == "Não confirmado":
                    # Construir o XPath para o item na posição correspondente
                    item_xpath = f'//*[@id="confirmar-procedimentos-modal"]/div/div/div[2]/div[2]/div/div[2]/div/div[{position}]'
                    try:
                        # Localizar o item correspondente
                        item = self.driver.find_element(By.XPATH, item_xpath)
                        logging.info(f"Procedimento na posição {position} não está confirmado. Confirmando agora...")

                        # Dentro desse item, localizar o elemento para clicar
                        # O elemento é um XPath fornecido por: //*[@id="span-cartao-magnetico"]/span[1]
                        
                        try:
                            confirm_button = item.find_element(By.XPATH, './/*[@id="span-cartao-magnetico"]/span[1]')
                        except NoSuchElementException:
                            # Se não encontrado dentro do item, procurar no contexto global
                            confirm_button = self.driver.find_element(By.XPATH, '//*[@id="span-cartao-magnetico"]/span[1]')

                        confirm_button.click()
                        logging.info(f"Botão de confirmar clicado na posição {position}.")

                        # Identificação para interações adicionais para a confirmaçao do atendimento.
                        # -------------------------------------------------
                        # Após clicar no botão, identificar o campo que se abre
                        try:
                            logging.info("Tentando localizar o campo de número da carteira após a confirmação.")

                            # Aguarde até que o campo esteja visível
                            campo_carteira = WebDriverWait(self.driver, 10).until(
                                EC.visibility_of_element_located((By.XPATH, '//*[@id="numeroDaCarteiraConfirmacao"]'))
                            )
                            logging.info("Campo 'numeroDaCarteiraConfirmacao' localizado com sucesso.")

                            # Obter o valor da coluna "CARTEIRINHA" do Excel para a linha atual
                            numero_carteira = self.data_handler.get_value(self.row_index, 'CARTEIRINHA')
                            if not numero_carteira:
                                raise Exception("Número da carteira não encontrado no Excel para a linha atual.")

                            # Preencher o campo com o valor extraído do Excel
                            campo_carteira.send_keys(numero_carteira)

                            logging.info(f"Campo 'numeroDaCarteiraConfirmacao' preenchido com o valor: {numero_carteira}")

                            # Aguarde 1 segundo
                            time.sleep(1)

                            # Simular a seta para baixo e pressionar Enter
                            campo_carteira.send_keys(Keys.ARROW_DOWN)
                            campo_carteira.send_keys(Keys.ENTER)
                            logging.info("Seta para baixo e Enter pressionados para selecionar a opção correta.")

                            # Localizar e clicar no botão "Confirmar"
                            botao_confirmar = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.XPATH, '//*[@id="indentificar-confirmar-procedimentos-modal"]/div/div/div[3]/div/button[2]'))
                            )
                            botao_confirmar.click()
                            logging.info("Botão de confirmação clicado com sucesso após preencher o número da carteira.")

                        except Exception as e:
                            logging.error(f"Erro ao interagir com o campo 'numeroDaCarteiraConfirmacao': {e}")
                            # Atualizar a coluna 'ERRO' no Excel com a mensagem de erro
                            self.data_handler.update_value(self.row_index, 'ERRO', f"Erro no campo 'numeroDaCarteiraConfirmacao': {e}")
                            self.data_handler.save()

                        # Opcional: Após as interações adicionais, você pode atualizar o status
                        # Aguardar até que o status mude para "Confirmado {data}"
                        status_element = item.find_element(By.XPATH, './/span[starts-with(@data-bind, "text: IsConfirmado()")]')
                        WebDriverWait(self.driver, 10).until(
                            lambda driver: status_element.text.strip().startswith("Confirmado")
                        )
                        updated_status = status_element.text.strip()
                        logging.info(f"Novo status do procedimento na posição {position}: {updated_status}")

                        # Atualizar o status na lista
                        self.confirmation_status_list[idx] = updated_status

                    except Exception as e:
                        logging.error(f"Erro ao confirmar o procedimento na posição {position}: {e}")
                        # Decida se deseja continuar ou não
                        # Neste caso, como só processamos o primeiro, podemos sair do loop
                        break

                    # Após processar o primeiro "Não confirmado", interromper o loop
                    break
                else:
                    logging.info(f"Procedimento na posição {position} já está confirmado.")

            logging.info("Processamento do primeiro procedimento não confirmado concluído.")

            # Atualizar a coluna 'CONFIRMACOES' no Excel após a confirmação
            confirmacoes_texto = "; ".join(self.confirmation_status_list)
            self.data_handler.update_value(self.row_index, 'CONFIRMACOES', confirmacoes_texto)
            self.data_handler.save()

        except Exception as e:
            logging.error(f"Erro ao processar o procedimento não confirmado: {e}")
            return





    def fechar_alerta_notificacao(self):
        """Fecha o alerta de notificação se estiver presente."""
        try:
            logging.info("Verificando se o alerta de notificação está presente.")
            # Esperar um tempo fixo conhecido antes de tentar encontrar o alerta
            time.sleep(1.5)  
            # Tentar localizar o elemento de modo fixo considerando que ele já exista
            alerta_close_button = self.driver.find_element(By.XPATH, "//i[contains(@class, 'fa-times') and contains(@class, 'close')]")
            alerta_close_button.click()
            logging.info("Alerta de notificação fechado com sucesso na tentativa inicial.")
        except NoSuchElementException:
            logging.info("Alerta de notificação não encontrado na tentativa inicial. Tentando novamente com WebDriverWait.")
            try:
                # Se não encontrado, tentar novamente usando WebDriverWait que irá esperar o elemento está presente
                alerta_close_button = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, "//i[contains(@class, 'fa-times') and contains(@class, 'close')]"))
                )
                alerta_close_button.click()
                logging.info("Alerta de notificação fechado com sucesso após usar WebDriverWait.")
            except TimeoutException:
                logging.info("Nenhum alerta de notificação encontrado após usar WebDriverWait.")
        except Exception as e:
            logging.error(f"Erro ao tentar fechar o alerta de notificação: {e}")


    def scroll_into_view(self):
        """Rola a página para visualizar o elemento necessário após processamento."""
        try:
            logging.info("Realizando scrollIntoView para o próximo processamento.")
            self.driver.execute_script("window.scrollTo(0, 0);")
            # Localizar o elemento 'guia_input'
            #guia_input = self.driver.find_element(By.CSS_SELECTOR, 'div.input-group > input.form-control.small')
            # Rolar para o elemento
            #self.driver.execute_script("arguments[0].scrollIntoView(true);", guia_input)
            time.sleep(1)
        except Exception as e:
            logging.error(f"Erro ao executar scrollIntoView: {e}")

# Exemplo de execução
if __name__ == "__main__":
    # Defina o caminho do arquivo e o nome da planilha
    file_path = r"C:\Users\SUPERVISÃO ADM\Desktop\RPA_verificação_ipasgo\planilhas\Base_confirmação.xlsx"
    sheet_name = 'Planilha1'

    # Crie uma instância de DataHandler
    data_handler = DataHandler(file_path, sheet_name)

    # Crie uma instância de VerificationIPASGO, passando o data_handler
    automacao = VerificationIPASGO(data_handler)

    # Defina o intervalo de linhas que deseja processar (números de linhas do Excel, incluindo o cabeçalho)
    start_line = 2 # Por exemplo, para começar na linha 508 do Excel
    end_line = len(data_handler.df) + 1  # Até a linha 509 do Excel

    # Converter números de linha do Excel para índices do pandas
    start_idx = start_line - 2  # Subtraia 2 para alinhar com o índice do pandas
    end_idx = end_line - 2

    try:
        # Faça o login apenas uma vez
        automacao.acessar_portal_ipasgo()

        # Itere sobre as linhas e processe cada uma
        for idx in range(start_idx, end_idx):
            automacao.row_index = idx
            excel_line_number = idx + 2  # Para correspondência com a linha do Excel
            logging.info(f"Iniciando o processamento da linha {excel_line_number}")

            try:
                automacao.executar_fluxo_para_linha()
                # Salve as alterações após processar cada linha
                data_handler.save()
            except Exception as e:
                error_message = getattr(e, 'msg', str(e))
                logging.error(f"Erro ao processar a linha {excel_line_number}: {error_message}")
                # Atualiza a coluna 'ERRO' no Excel
                data_handler.update_value(idx, 'ERRO', error_message)
                data_handler.save()
                # Continue para a próxima linha

    finally:
        # Feche o WebDriver após a execução
        automacao.driver.quit()
