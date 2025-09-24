# New version
# -*- coding: utf-8 -*-
"""
BrainEstar — Visualizador de EDF (tema claro)
================================================================
Objetivo geral
--------------
Este script implementa um **visualizador de sinais EEG em arquivos EDF** com uma
interface moderna em **PySide6 (Qt)** e renderização eficiente com **PyQtGraph**.

Recursos principais
-------------------
• Abertura de arquivos EDF/BDF com **MNE-Python** (em thread separada para manter a UI fluida).
• Filtro base global (0.1–60 Hz) aplicado no carregamento para remoção de DC e altas frequências.
• **Filtros extras** opcionais (Notch 50/60 Hz e bandas Delta/Teta/Alfa/Beta/Gama) aplicados **somente
  na janela visível** a cada redraw, reduzindo consumo de CPU/RAM.
• Painel de canais com busca e mapeamento **nome → índice**.
• Timeline com controle de **janela temporal**, **zoom** e **escala em µV/div** para amplitude.
• **Setinhas de navegação contínua** (◀ ▶) que, ao segurar, “andam” continuamente na linha do tempo.
• Renderização com **decimação adaptativa** = redução da taxa de amostragem (Frequencia) de um sinal ou a quantidade de dados de um modelo de forma 
seletiva e inteligente, de acordo com o conteúdo da informação (≈2000 pontos por traço) para manter FPS alto.
• Branding BrainEstar (tema claro) com **logo**: tenta arquivo externo (logo.ico) e usa **fallback embutido** (base64) se faltar.
• **HiDPI** habilitado para ícones e fontes nítidos.

Arquitetura
-----------
• `EEGDataSource`: backend de dados (leitura EDF, metadados, filtros e extração de janelas).
• `ChannelPanel`: painel de seleção/filtragem de canais (com busca de texto).
• `FilterPanel`: painel de filtros (bandas e notch) com botão de limpar.
• `Timeline`: navegação temporal (seek com debounce, zoom, µV/div e **setas com auto-repeat**).
• `SignalView`: área de desenho eficiente, rótulos por canal no eixo Y e dica de escala (µV/div).
• `LoadWorker`: worker executado em `QThread` para leitura de arquivo sem travar a UI.
• `MainWindow`: integra tudo, conecta sinais e mantém estado global da aplicação.

Observações de uso/manutenção
-----------------------------
• Esta versão assume que o filtro base FIR (0.1–60 Hz) é adequado para o fluxo. Ajuste conforme necessário.
• O objeto `Annotation` está definido para futuras anotações/labels de eventos mas ainda **não é utilizado**.
• Para empacotar com PyInstaller, garanta que `logo.ico` esteja ao lado do executável (ou será usado o fallback base64).
"""

from __future__ import annotations # Permite anotações de tipo avançadas (Python 3.7+)

# Bibliotecas padrão
import sys # Oferece acesso a variáveis e funções que interagem diretamente com o interpretador e o ambiente de execução
import os # Fornece uma maneira portátil de usar funcionalidades dependentes do sistema operacional
import math # Fornece acesso a funções matemáticas definidas pelo padrão C
import base64 # Fornece funções para codificação e decodificação de dados em base64 (imagens embutidas)
from dataclasses import dataclass # Simplifica a criação de classes que são principalmente "sacos de dados"
from typing import List, Optional, Tuple # Fornece suporte para anotações de tipo (listas, tuplas, opcionais etc.)
from pathlib import Path # Fornece uma maneira orientada a objetos de trabalhar com caminhos de arquivos e diretórios

# Numérico e EEG
import numpy as np # Biblioteca fundamental para computação científica com arrays/matrizes
import mne  # Biblioteca para leitura/tratamento de EEG/MEG/ECG (suporte a EDF/BDF etc.)

# UI/Gráficos
from PySide6 import QtCore, QtGui, QtWidgets  # Toolkit Qt para a interface (widgets, sinais e slots)
import pyqtgraph as pg  # Biblioteca de gráficos 2D acelerados (ótima para sinais contínuos)


# =========================
#  Branding (tema claro)
# =========================
# Paleta de cores BrainEstar (ajuste conforme identidade visual)
BR_COLORS = {
    "primary_blue": "#2E1E8B",       # Azul principal (títulos, traços etc.)
    "accent_magenta": "#E9407A",     # Acento (botões primários, gradientes)
    "bg_light": "#FAFAFA",           # Fundo da janela
    "surface_light": "#FFFFFF",      # Cartões/painéis (GroupBox)
    "text_dark": "#111827",          # Texto principal
    "border_light": "#E5E7EB",       # Bordas suaves
}

# Gradiente aplicado na ToolBar superior
GRADIENT_CSS = f"""
background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0,
stop:0 {BR_COLORS['primary_blue']}, stop:1 {BR_COLORS['accent_magenta']});
"""

# Stylesheet global da aplicação (Qt CSS)
APP_STYLESHEET = f"""
QMainWindow {{ background: {BR_COLORS['bg_light']}; color: {BR_COLORS['text_dark']}; }}
QToolBar {{ {GRADIENT_CSS} border:none; padding:6px; }}
QStatusBar {{ background:{BR_COLORS['surface_light']}; border-top:1px solid {BR_COLORS['border_light']}; }}
QGroupBox {{ background:{BR_COLORS['surface_light']}; border:1px solid {BR_COLORS['border_light']};
            border-radius:8px; margin-top:16px; }}
QGroupBox::title {{ subcontrol-origin: margin; left:12px; padding:0 4px; }}
QPushButton#primary {{ background:{BR_COLORS['accent_magenta']}; color:white; border:none; border-radius:8px; padding:8px 12px; }}
QPushButton#secondary {{ background:transparent; color:{BR_COLORS['primary_blue']}; border:1px solid {BR_COLORS['primary_blue']};
                        border-radius:8px; padding:6px 10px; }}
QLineEdit, QComboBox, QListWidget, QSpinBox, QDoubleSpinBox, QSlider {{
    background:{BR_COLORS['surface_light']}; border:1px solid {BR_COLORS['border_light']}; border-radius:8px; padding:6px; }}
"""


# =========================
#  Logo embutida (fallback)
# =========================
LOGO_BASE64 = b"""iVBORw0KGgoAAAANSUhEUgAAAMgAAABkCAIAAABM5OhcAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAEpmlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSfvu78nIGlkPSdXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQnPz4KPHg6eG1wbWV0YSB4bWxuczp4PSdhZG9iZTpuczptZXRhLyc+CjxyZGY6UkRGIHhtbG5zOnJkZj0naHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyc+CgogPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9JycKICB4bWxuczpBdHRyaWI9J2h0dHA6Ly9ucy5hdHRyaWJ1dGlvbi5jb20vYWRzLzEuMC8nPgogIDxBdHRyaWI6QWRzPgogICA8cmRmOlNlcT4KICAgIDxyZGY6bGkgcmRmOnBhcnNlVHlwZT0nUmVzb3VyY2UnPgogICAgIDxBdHRyaWI6Q3JlYXRlZD4yMDI1LTA4LTEyPC9BdHRyaWI6Q3JlYXRlZD4KICAgICA8QXR0cmliOkV4dElkPjBkZWM5MDA0LWEwODItNDkwNC1iYjJjLWFkZThmOWQxNGM1NzwvQXR0cmliOkV4dElkPgogICAgIDxBdHRyaWI6RmJJZD41MjUyNjU5MTQxNzk1ODA8L0F0dHJpYjpGYklkPgogICAgIDxBdHRyaWI6VG91Y2hUeXBlPjI8L0F0dHJpYjpUb3VjaFR5cGU+CiAgICA8L3JkZjpsaT4KICAgPC9yZGY6U2VxPgogIDwvQXR0cmliOkFkcz4KIDwvcmRmOkRlc2NyaXB0aW9uPgoKIDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PScnCiAgeG1sbnM6ZGM9J2h0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvJz4KICA8ZGM6dGl0bGU+CiAgIDxyZGY6QWx0PgogICAgPHJkZjpsaSB4bWw6bGFuZz0neC1kZWZhdWx0Jz5DQVBBIFNJU1RFTUEgLSAxPC9yZGY6bGk+CiAgIDwvcmRmOkFsdD4KICA8L2RjOnRpdGxlPgogPC9yZGY6RGVzY3JpcHRpb24+CgogPHJkZjpEZXNjcmlwdGlvbiBy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"""


def load_logo_pixmap() -> QtGui.QPixmap:
    """Carrega o logotipo como QPixmap.

    Estratégia de busca:
    1) Primeiro tenta carregar um arquivo **logo.ico** localizado ao lado do executável (PyInstaller)
       ou do script `.py`. Para builds PyInstaller, `sys._MEIPASS` aponta para a pasta temporária
       onde os arquivos empacotados são extraídos em runtime.
    2) Se o arquivo externo não existir, usa o **LOGO_BASE64** embutido (fallback), evitando
       dependência do arquivo físico.
    """
    pm = QtGui.QPixmap()
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))  # Compatível com PyInstaller e execução direta
    ico = base / "logo.ico"
    if ico.exists():
        pm.load(str(ico))
        return pm
    # Fallback embutido (base64 → bytes → QPixmap)
    data = base64.b64decode(LOGO_BASE64)
    pm.loadFromData(data)
    return pm


# =========================
#  Dados / Filtros
# =========================
@dataclass
class Annotation:
    """Estrutura para **anotações** no sinal (não utilizada nesta versão).

    Versões futuras para marcar eventos: artefatos, estímulos, spikes etc.
    """
    t_start: float
    t_end: float
    label: str
    notes: str = ""


class EEGDataSource(QtCore.QObject):
    """Backend de dados EEG.

    Responsável por:
    • Carregar o arquivo EDF/BDF via MNE-Python.
    • Padronizar nomes de canais e guardar metadados (fs, duração, lista de canais).
    • Aplicar um **filtro base global** (0.1–60 Hz) no `Raw` carregado.
    • Expor **filtros extras** (notch/bandas) aplicados **sob demanda** em `get_window()` apenas no
      segmento visível (eficiência de CPU/RAM).
    • Fornecer janelas de dados já em **microvolts (µV)**, prontas para plotar.
    """

    # Sinais Qt:
    data_loaded = QtCore.Signal()       # Emite quando o EDF é carregado e filtrado (base)
    filters_applied = QtCore.Signal()   # Emite quando filtros extras mudam (solicita redraw)

    def __init__(self):
        super().__init__()
        self.raw: Optional[mne.io.BaseRaw] = None  # Objeto Raw do MNE (sinais contínuos)
        self.fs: float = 0.0                       # Taxa de amostragem (Hz)
        self.duration_s: float = 0.0               # Duração total (s)
        self.channel_names: List[str] = []         # Lista de nomes dos canais (em UPPER)
        # Configurações de filtros extras (aplicados por janela):
        self.notch: Optional[int] = None                # 50 / 60 / None
        self.band: Optional[Tuple[float, float]] = None # (low, high) ou None

    # ---------- Ciclo de vida dos dados ----------
    def load(self, path: str):
        """Lê o EDF/BDF, normaliza canais, aplica filtro base e avisa que os dados estão prontos.

        Parâmetros
        ----------
        path : str
            Caminho do arquivo EDF/BDF.
        """
        # Lê o arquivo já com preload=True para ter acesso rápido ao buffer em RAM
        self.raw = mne.io.read_raw_edf(path, preload=True, verbose=False)

        # Normaliza nomes para UPPER (evita confusão entre c3 e C3, por exemplo)
        self.raw.rename_channels({ch: ch.upper() for ch in self.raw.ch_names})

        # Metadados úteis
        self.fs = float(self.raw.info["sfreq"])             # Hz
        self.duration_s = self.raw.n_times / self.fs         # s
        self.channel_names = list(self.raw.ch_names)

        # Filtro base global: remove DC e limita altas frequências (suave)
        # Observação: aplicado no `Raw` inteiro (uma vez no carregamento).
        self.raw.filter(l_freq=0.1, h_freq=60.0, method="fir", verbose=False)

        # Informa para a UI que os dados estão prontos
        self.data_loaded.emit()

    def apply_filters(self):
        """Notifica que parâmetros de filtros extras mudaram.

        O desenho (`SignalView.redraw`) aplicará os filtros **apenas na janela atual**.
        """
        if self.raw is None:
            return
        self.filters_applied.emit()

    def get_window(self, t0: float, window_s: float, picks: List[int]):
        """Extrai dados **da janela visível** e aplica filtros extras apenas neste segmento.

        Retorna uma tupla `(seg, times)` onde `seg` tem shape [n_canais, n_amostras] em µV e `times` está em segundos.

        Parâmetros
        ----------
        t0 : float
            Tempo inicial da janela (s).
        window_s : float
            Largura da janela (s).
        picks : List[int]
            Índices dos canais selecionados para exibição.
        """
        if self.raw is None or not picks:
            return np.zeros((0, 0)), np.zeros(0)

        # Converte t0 e (t0+janela) para índices, garantindo limites válidos
        start_idx = int(np.clip(t0, 0, self.duration_s) * self.fs)
        stop_idx  = int(np.clip(t0 + window_s, 0, self.duration_s) * self.fs)
        if stop_idx <= start_idx:
            stop_idx = min(start_idx + 1, int(self.duration_s * self.fs))  # Pelo menos 1 amostra

        # Obtém segmento bruto (em volts) e converte para microvolts (µV)
        seg = self.raw.get_data(picks=picks, start=start_idx, stop=stop_idx, verbose=False) * 1e6

        # Aplica filtros extras **apenas no segmento atual** (eficiência)
        if self.notch in (50, 60):
            seg = mne.filter.notch_filter(seg, Fs=self.fs, freqs=self.notch, verbose=False)
        if self.band:
            l, h = self.band
            seg = mne.filter.filter_data(seg, sfreq=self.fs, l_freq=l, h_freq=h, method="fir", verbose=False)

        # Vetor de tempo correspondente ao segmento
        times = np.arange(start_idx, stop_idx) / self.fs
        return seg, times


# =========================
#  Painel de Canais (OTIMIZADO)
# =========================
class ChannelPanel(QtWidgets.QGroupBox):
    """Painel de seleção de canais.

    Recursos:
    • **Busca** por nome (filtro de visibilidade dos checkboxes).
    • Botões "Selecionar todos" / "Limpar seleção" que respeitam a busca (apenas itens visíveis).
    • Mapeamento **nome → índice** para recuperar rapidamente o `pick` do MNE.
    • Emite `channels_changed(List[int])` sempre que a seleção visível muda.
    """

    channels_changed = QtCore.Signal(list)

    def __init__(self, ds: EEGDataSource):
        super().__init__("Canais")
        self.ds = ds
        self._name_to_idx: dict[str, int] = {}  # Mapa nome→índice para acesso O(1)

        # Caixa de busca (filtra por texto)
        self.search = QtWidgets.QLineEdit(placeholderText="Buscar canal (ex.: C3)")

        # Área com rolagem que contém os checkboxes de canais
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QtWidgets.QWidget()
        self.channel_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.channel_layout.setAlignment(QtCore.Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        # Ações rápidas
        btn_all = QtWidgets.QPushButton("Selecionar todos"); btn_all.setObjectName("secondary")
        btn_none = QtWidgets.QPushButton("Limpar seleção"); btn_none.setObjectName("secondary")

        # Conexões
        btn_all.clicked.connect(self.select_all)
        btn_none.clicked.connect(self.clear_selection)
        self.search.textChanged.connect(self._filter_channels)

        # Layout principal do GroupBox
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.scroll_area, 1)
        hl = QtWidgets.QHBoxLayout(); hl.addWidget(btn_all); hl.addWidget(btn_none)
        layout.addLayout(hl)

    def populate(self):
        """Preenche o painel com checkboxes para cada canal carregado."""
        # Remove widgets anteriores (se houver)
        for i in reversed(range(self.channel_layout.count())):
            w = self.channel_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        # Mapeia nomes para índices uma única vez
        self._name_to_idx = {n: i for i, n in enumerate(self.ds.channel_names)}

        # Cria um checkbox por canal; inicia todos marcados
        for name in self.ds.channel_names:
            cb = QtWidgets.QCheckBox(name)
            cb.setChecked(True)
            cb.toggled.connect(self._emit_selected)
            self.channel_layout.addWidget(cb)

        # Emite seleção inicial (todos visíveis marcados)
        self._emit_selected()

    def _filter_channels(self, text: str):
        """Filtra a visibilidade dos checkboxes com base no texto digitado."""
        t = text.upper()
        for i in range(self.channel_layout.count()):
            cb: QtWidgets.QCheckBox = self.channel_layout.itemAt(i).widget()
            cb.setHidden(t not in cb.text().upper())
        self._emit_selected()

    def select_all(self):
        """Marca **todos os checkboxes visíveis**."""
        for i in range(self.channel_layout.count()):
            cb: QtWidgets.QCheckBox = self.channel_layout.itemAt(i).widget()
            if not cb.isHidden():
                cb.setChecked(True)
        self._emit_selected()

    def clear_selection(self):
        """Desmarca **todos os checkboxes visíveis**."""
        for i in range(self.channel_layout.count()):
            cb: QtWidgets.QCheckBox = self.channel_layout.itemAt(i).widget()
            if not cb.isHidden():
                cb.setChecked(False)
        self._emit_selected()

    def _emit_selected(self):
        """Coleta índices dos canais **visíveis e marcados** e emite o sinal `channels_changed`."""
        selected_picks = []
        for i in range(self.channel_layout.count()):
            cb: QtWidgets.QCheckBox = self.channel_layout.itemAt(i).widget()
            if not cb.isHidden() and cb.isChecked():
                idx = self._name_to_idx.get(cb.text())
                if idx is not None:
                    selected_picks.append(idx)
        self.channels_changed.emit(selected_picks)


# =========================
#  Painel de Filtros
# =========================
class FilterPanel(QtWidgets.QGroupBox):
    """Painel para configurar **filtros extras** (bandas e notch).

    • Bandas (checkboxes) podem ser combinadas: o código calcula o intervalo [min, max] da união
      simples e aplica como passa-faixa.
    • Notch selecionável entre 50/60 Hz (ou sem notch).
    • Botão "Limpar" remove todas as seleções e volta ao estado bypass (sem filtros extras).
    • Cada alteração chama `ds.apply_filters()`, que sinaliza a necessidade de redesenho.
    """

    filter_changed = QtCore.Signal()

    def __init__(self, ds: EEGDataSource):
        super().__init__("Filtros")
        self.ds = ds

        # Checkboxes de bandas frequenciais
        self.delta = QtWidgets.QCheckBox("Delta (0.5–4)")
        self.theta = QtWidgets.QCheckBox("Teta (4–8)")
        self.alpha = QtWidgets.QCheckBox("Alfa (8–13)")
        self.beta  = QtWidgets.QCheckBox("Beta (13–30)")
        self.gamma = QtWidgets.QCheckBox("Gama (30–45)")

        # Opções de notch (rede elétrica)
        self.notchNone = QtWidgets.QRadioButton("Sem Notch"); self.notchNone.setChecked(True)
        self.notch50 = QtWidgets.QRadioButton("Notch 50 Hz")
        self.notch60 = QtWidgets.QRadioButton("Notch 60 Hz")

        # Botão para limpar tudo
        self.bypass = QtWidgets.QPushButton("Limpar"); self.bypass.setObjectName("secondary")

        # Layout em grade
        grid = QtWidgets.QGridLayout(self)
        for r, w in enumerate([self.delta, self.theta, self.alpha, self.beta, self.gamma]):
            grid.addWidget(w, r, 0, 1, 2)
            w.toggled.connect(self._update_band)

        grid.addWidget(QtWidgets.QLabel("Rede:"), 5, 0)
        net = QtWidgets.QHBoxLayout()
        for rb in (self.notchNone, self.notch50, self.notch60):
            net.addWidget(rb)
            rb.toggled.connect(self._update_notch)
        netw = QtWidgets.QWidget(); netw.setLayout(net)
        grid.addWidget(netw, 5, 1)

        grid.addWidget(self.bypass, 6, 0, 1, 2)
        self.bypass.clicked.connect(self._bypass)

    # ------ Callbacks de UI ------
    def _update_band(self):
        """Calcula a banda combinada (união simples) e aplica no `EEGDataSource`.

        Ex.: se Alfa e Beta estiverem marcadas, a banda final será (8, 30).
        """
        bands = []
        if self.delta.isChecked(): bands.append((0.5, 4))
        if self.theta.isChecked(): bands.append((4, 8))
        if self.alpha.isChecked(): bands.append((8, 13))
        if self.beta.isChecked():  bands.append((13, 30))
        if self.gamma.isChecked(): bands.append((30, 45))
        self.ds.band = (min(b[0] for b in bands), max(b[1] for b in bands)) if bands else None
        self.ds.apply_filters()

    def _update_notch(self):
        """Atualiza o notch (50/60 Hz) ou None, e solicita redraw."""
        self.ds.notch = 50 if self.notch50.isChecked() else 60 if self.notch60.isChecked() else None
        self.ds.apply_filters()

    def _bypass(self):
        """Reseta todas as seleções (sem filtros extras)."""
        for cb in (self.delta, self.theta, self.alpha, self.beta, self.gamma):
            cb.setChecked(False)
        self.notchNone.setChecked(True)
        self.ds.band = None
        self.ds.notch = None
        self.ds.apply_filters()


# =========================
#  Timeline / Navegação
# =========================
class Timeline(QtWidgets.QGroupBox):
    """Controle de navegação temporal e escala de amplitude.

    Elementos:
    • Slider horizontal para **seek** (com debounce de 100 ms para evitar redesenhos excessivos durante o arraste).
    • Campo de **Janela (s)** com botões de Zoom (Zoom −/Zoom +), onde **Zoom +** aumenta a janela (mais tempo na tela).
    • Campo de **Escala (µV/div)** com botões Amp −/Amp + (semântica de osciloscópio):
      – Amp + → µV/div menor → traços **maiores** na tela (maior ganho visual).
      – Amp − → µV/div maior → traços **menores** na tela.
    • **Setinhas ◀ ▶ com auto-repeat** para “andar” continuamente pela linha do tempo ao segurar.
    """

    # Sinais disparados para comunicação com SignalView
    seek_changed = QtCore.Signal(float)   # novo t0 (s)
    window_changed = QtCore.Signal(float) # nova janela (s)
    amp_changed = QtCore.Signal(float)    # novo µV/div

    def __init__(self, ds: EEGDataSource):
        super().__init__("Navegação Temporal")
        self.ds = ds
        self.window_s = 5.0  # Janela inicial (s)

        # Slider para posição temporal (o range é configurado após o load)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.setSingleStep(1)
        self.lbl_pos = QtWidgets.QLabel("t = 0.0 s")

        # Controles de Zoom (UX: Zoom + = janela maior; Zoom − = janela menor)
        self.zoom_in  = QtWidgets.QPushButton("Zoom -")  # reduz a janela ⇒ mais detalhes
        self.zoom_in.setObjectName("secondary")
        self.zoom_out = QtWidgets.QPushButton("Zoom +")  # aumenta a janela ⇒ mais contexto
        self.zoom_out.setObjectName("secondary")

        # Campo da janela (somente exibição/edição; sem botões de spin visíveis)
        self.window_input = QtWidgets.QDoubleSpinBox()
        self.window_input.setSuffix(" s")
        self.window_input.setMinimum(1.0)
        self.window_input.setMaximum(120.0)
        self.window_input.setSingleStep(1.0)
        self.window_input.setValue(self.window_s)
        self.window_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)

        # Controles de amplitude (µV/div)
        self.amp_minus_btn = QtWidgets.QPushButton("Amp +")  # µV/div menor ⇒ traço maior
        self.amp_minus_btn.setObjectName("secondary")
        self.amp_plus_btn  = QtWidgets.QPushButton("Amp -")  # µV/div maior ⇒ traço menor
        self.amp_plus_btn.setObjectName("secondary")
        self.amp_input = QtWidgets.QDoubleSpinBox()
        self.amp_input.setSuffix(" µV/div")
        self.amp_input.setMinimum(1.0)
        self.amp_input.setMaximum(2000.0)
        self.amp_input.setSingleStep(10.0)
        self.amp_input.setValue(50.0)  # Padrão comum em traçados clínicos
        self.amp_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)

        # Botões de passo contínuo (setinhas esquerda/direita) com auto-repeat
        self.step_left = QtWidgets.QToolButton()
        self.step_left.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowBack))
        self.step_left.setToolTip("Andar para trás continuamente (segure)")
        self.step_left.setAutoRepeat(True)
        self.step_left.setAutoRepeatDelay(300)      # ms até começar a repetir
        self.step_left.setAutoRepeatInterval(50)    # ms entre repetições

        self.step_right = QtWidgets.QToolButton()
        self.step_right.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowForward))
        self.step_right.setToolTip("Andar para frente continuamente (segure)")
        self.step_right.setAutoRepeat(True)
        self.step_right.setAutoRepeatDelay(300)
        self.step_right.setAutoRepeatInterval(50)

        # Linha superior (janela + escala + setas)
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(self.step_left)   # ◀
        top_layout.addWidget(self.step_right)  # ▶
        top_layout.addSpacing(8)
        top_layout.addWidget(QtWidgets.QLabel("Janela:"))
        top_layout.addWidget(self.window_input)
        top_layout.addWidget(self.zoom_in)
        top_layout.addWidget(self.zoom_out)
        top_layout.addSpacing(12)
        top_layout.addWidget(QtWidgets.QLabel("Escala:"))
        top_layout.addWidget(self.amp_input)
        top_layout.addWidget(self.amp_plus_btn)
        top_layout.addWidget(self.amp_minus_btn)
        top_layout.addStretch()

        # Layout principal do GroupBox
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top_layout)
        lay.addWidget(self.slider)
        lay.addWidget(self.lbl_pos)

        # Conexões de sinais
        self.slider.valueChanged.connect(self._queue_seek)   # enquanto arrasta, só atualiza label + inicia debounce
        self.slider.sliderReleased.connect(self._emit_seek_now)  # ao soltar, busca imediata
        self.window_input.valueChanged.connect(self._apply_window)
        self.zoom_in.clicked.connect(self._zoom_in)
        self.zoom_out.clicked.connect(self._zoom_out)
        self.amp_input.valueChanged.connect(self._apply_amp)
        self.amp_minus_btn.clicked.connect(self._amp_minus)
        self.amp_plus_btn.clicked.connect(self._amp_plus)

        # Setinhas: deslocamento contínuo (auto-repeat)
        self.step_left.clicked.connect(lambda: self._nudge(-self._step_amount()))
        self.step_right.clicked.connect(lambda: self._nudge(self._step_amount()))

        # Timer de debounce para o seek (evita redraws excessivos durante arraste)
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(100)  # ms
        self._debounce.timeout.connect(self._emit_seek_now)

    def configure(self):
        """Configura o range do slider de acordo com a duração do arquivo carregado."""
        if self.ds.raw is None:
            return
        self.slider.blockSignals(True)
        # Range do slider em décimos de segundo (x10) para ter resolução de 0.1 s
        self.slider.setMaximum(int(max(0.0, self.ds.duration_s - self.window_s) * 10))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self._emit_seek_now()  # posiciona na origem

    # --- Navegação contínua via setinhas ---
    def _step_amount(self) -> float:
        """Tamanho do passo em segundos ao repetir a setinha.
        Proporcional à janela para sentir 'mesma velocidade' em qualquer zoom."""
        return max(0.05, self.window_s * 0.05)  # 5% da janela, mínimo 50 ms

    def _nudge(self, delta_s: float):
        """Desloca a janela delta_s segundos, aplicando limites e emitindo seek imediato."""
        if self.ds.raw is None:
            return
        # Limites: [0, duração - janela]
        max_t0 = max(0.0, self.ds.duration_s - self.window_s)
        new_t0 = float(np.clip(self.slider.value() / 10.0 + delta_s, 0.0, max_t0))

        # Atualiza o slider em 'décimos de segundo' sem disparar debounce
        ticks = int(round(new_t0 * 10.0))
        self.slider.blockSignals(True)
        self.slider.setValue(ticks)
        self.slider.blockSignals(False)

        # Seek imediato (sem esperar o debounce)
        self._emit_seek_now()

    # ------ Callbacks internos ------
    def _queue_seek(self):
        """Atualiza label de tempo enquanto arrasta e inicia o timer de debounce."""
        t0 = self.slider.value() / 10.0
        self.lbl_pos.setText(f"t = {t0:.1f} s")
        self._debounce.start()

    def _emit_seek_now(self):
        """Emite o `seek_changed` imediatamente (chamado pelo debounce ou ao soltar o slider)."""
        t0 = self.slider.value() / 10.0
        self.lbl_pos.setText(f"t = {t0:.1f} s")
        self.seek_changed.emit(t0)

    def _apply_window(self, new_win: float):
        """Aplica uma **nova largura de janela** (s), reconfigura o slider e notifica ouvintes."""
        if self.ds.raw is None:
            return
        self.window_s = float(np.clip(new_win, 1.0, 120.0))
        self.window_changed.emit(self.window_s)
        self.configure()
        # Evita loops devido ao próprio setValue
        self.window_input.blockSignals(True)
        self.window_input.setValue(self.window_s)
        self.window_input.blockSignals(False)

    def _zoom_in(self):
        """Zoom − (janela menor → mais detalhe visual)."""
        self._apply_window(self.window_s * 0.8)

    def _zoom_out(self):
        """Zoom + (janela maior → mais contexto temporal)."""
        self._apply_window(self.window_s * 1.25)

    def _apply_amp(self, new_amp: float):
        """Emite mudança de **µV/div** para a área de sinais."""
        self.amp_changed.emit(new_amp)

    def _amp_minus(self):
        """Amp + (botão) → reduz µV/div (aumenta ganho visual)."""
        self.amp_input.setValue(self.amp_input.value() * 1.25)

    def _amp_plus(self):
        """Amp − (botão) → aumenta µV/div (reduz ganho visual)."""
        self.amp_input.setValue(self.amp_input.value() / 1.25)


# =========================
#  Área de Sinais (decimação no desenho)
# =========================
class SignalView(pg.PlotWidget):
    """Widget de plotagem com **PyQtGraph** para exibir os traçados dos canais.

    Estratégias de performance
    --------------------------
    • **Decimação**: limita os pontos exibidos a `max_points` (≈2000) por janela, controlando FPS.
    • **ClipToView** e **Downsampling** (se disponíveis): aceleração adicional no PyQtGraph.
    • **Filtros extras**: já aplicados em `EEGDataSource.get_window()` apenas no segmento atual.

    UX/Visual
    ---------
    • Grid x/y com alpha suave; eixo X em segundos, eixo Y com **rótulos por canal** (um por traço).
    • Offsets verticais uniformes entre traços; **escala µV/div** exibida no canto inferior direito.
    """

    def __init__(self, ds: EEGDataSource):
        super().__init__(background=None)
        self.ds = ds

        # Aparência dos eixos e da grade
        self.showGrid(x=True, y=True, alpha=0.6)
        self.getPlotItem().getViewBox().setBackgroundColor(None)
        for ax in ("left", "bottom"):
            self.getPlotItem().getAxis(ax).setPen(pg.mkPen(color=(180, 180, 180), width=1.2))

        # Rótulos e layout do PlotItem
        pi = self.getPlotItem()
        pi.getAxis("bottom").setLabel("Tempo (s)")
        pi.getAxis("left").setStyle(tickTextOffset=10, autoExpandTextSpace=True)
        pi.layout.setColumnFixedWidth(0, 60)  # Largura reservada p/ rótulos de canais

        # Estado de desenho
        self.curves: List[pg.PlotCurveItem] = []  # 1 curva por canal selecionado
        self.offset_uV = 100.0                    # Distância vertical entre traços (em µV * ganho)
        self.uv_per_div = 50.0                    # Escala inicial (µV/div)
        self.window_s = 5.0                       # Largura de janela atual (s)
        self.t0 = 0.0                             # Início da janela (s)
        self.picks: List[int] = []                # Índices de canais exibidos
        self.trace_pen = pg.mkPen(color=BR_COLORS["primary_blue"], width=1.25)

        self.max_points = 2000                    # Teto de pontos por traço para manter responsividade

        # Indicador de escala (µV/div) no canto inferior direito
        self.scaleText = pg.TextItem("", anchor=(1, 1), color=(80, 80, 80))
        self.addItem(self.scaleText)

    # ------ API chamada a partir da MainWindow/Timeline ------
    def set_uv_per_div(self, value: float):
        """Define a escala de amplitude (µV/div) e redesenha."""
        self.uv_per_div = float(np.clip(value, 1.0, 2000.0))
        self.redraw()

    def set_window(self, t0: float, window_s: float):
        """Atualiza a janela temporal e solicita redesenho."""
        self.t0 = t0
        self.window_s = window_s
        self.redraw()

    def set_picks(self, picks: List[int]):
        """Define os canais exibidos, recriando as curvas e rótulos Y."""
        self.picks = picks
        # Remove curvas anteriores
        for c in self.curves:
            self.removeItem(c)
        self.curves.clear()
        # Cria uma curva por canal selecionado
        for _ in self.picks:
            c = pg.PlotCurveItem(pen=self.trace_pen)
            # Recursos de aceleração (dependem da versão do PyQtGraph)
            if hasattr(c, "setClipToView"):
                c.setClipToView(True)
            if hasattr(c, "setDownsampling"):
                c.setDownsampling(auto=True, method="peak")
            self.addItem(c)
            self.curves.append(c)
        self._update_y_ticks()
        self.redraw()

    # ------ Utilidades internas ------
    def _y_offsets(self, n: int):
        """Retorna um vetor de offsets verticais (um por traço)."""
        return np.array([(n - i) * self.offset_uV for i in range(n)], dtype=float)

    def _update_y_ticks(self):
        """Atualiza o eixo Y com os nomes dos canais na posição do respectivo traço."""
        if not self.picks or self.ds.raw is None:
            self.getPlotItem().getAxis("left").setTicks([])
            return
        names = [self.ds.channel_names[p] for p in self.picks]
        offs = self._y_offsets(len(names))
        ticks = list(zip(offs, names))  # (posição_em_y, rótulo)
        self.getPlotItem().getAxis("left").setTicks([ticks])

    def _decimate(self, t: np.ndarray, y: np.ndarray):
        """Aplica uma decimação simples para limitar o número de pontos plotados.

        Mantém a proporção temporal usando um passo inteiro `step`.
        """
        n = y.shape[-1]
        if n <= self.max_points:
            return t, y
        step = int(math.ceil(n / self.max_points))
        return t[::step], y[..., ::step]

    def redraw(self):
        """Recalcula dados da janela atual e atualiza as curvas no gráfico."""
        if self.ds.raw is None or not self.picks:
            return

        # Extrai dados e tempos da janela atual (com filtros extras aplicados pelo DataSource)
        data, times = self.ds.get_window(self.t0, self.window_s, self.picks)
        if data.size == 0:
            return

        # Limita pontos para manter fluidez
        times, data = self._decimate(times, data)

        # Conversão de µV → pixels: ganho = offset_uV / (µV/div)
        amp_gain = self.offset_uV / self.uv_per_div
        n, _ = data.shape
        offs = self._y_offsets(n)
        y = (data * amp_gain) + offs[:, None]

        # Atualiza cada curva com seu respectivo traço
        for i, curve in enumerate(self.curves):
            curve.setData(times, y[i])

        # Ajusta ranges para enquadrar a janela e os traços com pequena folga
        self.setXRange(times[0], times[-1], padding=0)
        self.setYRange(offs.min() - self.offset_uV*0.5, offs.max() + self.offset_uV*0.5, padding=0)
        self._update_y_ticks()

        # Atualiza indicador de escala no canto inferior direito
        self.scaleText.setText(f"{self.uv_per_div:.0f} µV/div")
        self.scaleText.setPos(times[-1], offs.min() - self.offset_uV*0.5)


# =========================
#  Worker de carregamento (thread)
# =========================
class LoadWorker(QtCore.QObject):
    """Worker executado em **QThread** para carregar o EDF sem bloquear a UI.

    Emite `finished(path)` em caso de sucesso ou `error(msg)` em caso de exceção.
    """

    finished = QtCore.Signal(str)   # caminho do arquivo lido
    error = QtCore.Signal(str)      # mensagem de erro

    def __init__(self, ds: EEGDataSource, path: str):
        super().__init__()
        self._ds = ds
        self._path = path

    @QtCore.Slot()
    def run(self):
        """Executa a leitura do EDF dentro da thread."""
        try:
            self._ds.load(self._path)
            self.finished.emit(self._path)
        except Exception as e:
            self.error.emit(str(e))


# =========================
#  Main Window
# =========================
class MainWindow(QtWidgets.QMainWindow):
    """Janela principal que integra os painéis, gráficos e lógica de navegação."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("BrainEstar — Visualizador de EEG (EDF)")
        self.resize(1320, 840)
        self.setStyleSheet(APP_STYLESHEET)

        # Backend de dados
        self.ds = EEGDataSource()

        # ---- ToolBar superior com logo e botão Abrir ----
        tb = QtWidgets.QToolBar()
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)

        logo_w = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(logo_w)
        hl.setContentsMargins(0, 0, 0, 0)

        lbl = QtWidgets.QLabel()
        pm = load_logo_pixmap().scaledToHeight(28, QtCore.Qt.SmoothTransformation)
        lbl.setPixmap(pm)
        hl.addWidget(lbl)

        title = QtWidgets.QLabel("  BRAINESTAR — Visualizador de EEG")
        title.setStyleSheet("color:white; font-weight:600;")
        hl.addWidget(title)

        tb.addWidget(logo_w)
        tb.addSeparator()

        btn_open = QtWidgets.QPushButton("Abrir EDF…")
        btn_open.setObjectName("primary")
        tb.addWidget(btn_open)

        tb.addSeparator()
        self.meta = QtWidgets.QLabel("")  # Label para metadados do arquivo aberto (Fs, duração, nº de canais)
        self.meta.setStyleSheet("color:white;")
        tb.addWidget(self.meta)

        # ---- Área central: painéis à esquerda, sinal + timeline à direita ----
        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        H = QtWidgets.QHBoxLayout(central)
        left = QtWidgets.QVBoxLayout()
        right = QtWidgets.QVBoxLayout()

        # Painéis
        self.channels = ChannelPanel(self.ds)
        self.filters  = FilterPanel(self.ds)
        left.addWidget(self.channels, 2)
        left.addWidget(self.filters, 1)

        # Área de sinais e timeline
        self.signal = SignalView(self.ds)
        self.timeline = Timeline(self.ds)

        right.addWidget(self.signal, 6)
        right.addWidget(self.timeline, 2)

        H.addLayout(left, 3)
        H.addLayout(right, 7)

        # Barra de status inferior
        self.status = self.statusBar()

        # ---- Conexões de sinais entre componentes ----
        btn_open.clicked.connect(self.open_edf)  # Abrir arquivo
        self.ds.data_loaded.connect(self.on_loaded)  # Quando dados prontos
        self.channels.channels_changed.connect(self.signal.set_picks)  # Seleção de canais mudou
        self.ds.filters_applied.connect(self.signal.redraw)  # Filtros extras alterados (redesenha)
        self.timeline.seek_changed.connect(lambda t0: self.signal.set_window(t0, self.signal.window_s))
        self.timeline.window_changed.connect(lambda w: self.signal.set_window(self.signal.t0, w))
        self.timeline.amp_changed.connect(self.signal.set_uv_per_div)

        # Referências para a thread de load (evitam coleta prematura)
        self._load_thread: Optional[QtCore.QThread] = None
        self._load_worker: Optional[LoadWorker] = None

    # ----- Abertura de arquivo em thread separada -----
    def open_edf(self):
        """Abre diálogo de arquivo, cria `LoadWorker` em `QThread` e inicia a leitura."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir EDF", filter="EDF/BDF (*.edf *.bdf)")
        if not path:
            return
        self.status.showMessage("Carregando EDF, aguarde...")
        self.setEnabled(False)  # Desabilita UI temporariamente

        # Cria thread e worker e conecta sinais
        self._load_thread = QtCore.QThread(self)
        self._load_worker = LoadWorker(self.ds, path)
        self._load_worker.moveToThread(self._load_thread)

        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_load_ok)
        self._load_worker.error.connect(self._on_load_err)

        # Tear-down/limpeza automática ao terminar
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_worker.error.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._load_worker.deleteLater)
        self._load_thread.finished.connect(self._load_thread.deleteLater)

        self._load_thread.start()

    @QtCore.Slot(str)
    def _on_load_ok(self, path: str):
        """Callback de sucesso: reabilita UI, mostra metadados e atualiza status."""
        self.setEnabled(True)
        self.meta.setText(
            f"<b>{os.path.basename(path)}</b> — Fs {self.ds.fs:.1f} Hz • Duração {self.ds.duration_s/60:.1f} min • {len(self.ds.channel_names)} canais"
        )
        self.status.showMessage(f"Carregado: {path}")

    @QtCore.Slot(str)
    def _on_load_err(self, msg: str):
        """Callback de erro: reabilita UI, mostra MessageBox e atualiza status."""
        self.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Erro ao abrir", msg)
        self.status.showMessage("Falha ao carregar")

    # ----- Pós-load: inicializa painéis e timeline -----
    def on_loaded(self):
        """Chamado após `EEGDataSource.data_loaded`.

        • Popula painel de canais.
        • Seleciona todos os canais por padrão.
        • Inicializa a timeline (o que também dispara o primeiro redraw do gráfico).
        """
        self.channels.populate()
        self.signal.set_picks(list(range(len(self.ds.channel_names))))
        # Inicializa timeline (dispara window_changed e ajusta slider)
        self.timeline._apply_window(self.timeline.window_s)


# =========================
#  main()
# =========================

def main():
    """Ponto de entrada da aplicação."""
    # Ativa suporte HiDPI para melhor nitidez de ícones e texto
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # Cria a aplicação Qt e ajusta opções do PyQtGraph
    app = QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)  # Traços suavizados

    # Instancia e exibe a MainWindow
    w = MainWindow()
    w.showMaximized()

    # Loop principal
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
