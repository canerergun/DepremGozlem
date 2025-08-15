# deprem.py
# Tek dosya — Deprem Gözlem

from __future__ import annotations
import os, sys, json, time, sqlite3, tempfile, csv, logging, hashlib, secrets
from typing import List, Dict, Any, Optional, Tuple

import requests

# PySide6
from PySide6.QtCore import Qt, QTimer, QDate, QUrl, QSize, QRegularExpression, QThread, QObject, Signal
from PySide6.QtGui import QIcon, QAction, QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTabWidget, QDateEdit, QDoubleSpinBox, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QFormLayout, QSpinBox, QLineEdit, QMessageBox,
    QFileDialog, QSystemTrayIcon, QMenu, QSplitter, QInputDialog, QTableView, QAbstractItemView
)
from PySide6.QtCore import QSortFilterProxyModel

# WebEngine
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings
    HAS_WEBENGINE = True
except Exception:
    HAS_WEBENGINE = False

# QtMultimedia (Ses için)
try:
    from PySide6.QtMultimedia import QSoundEffect, QUrl
    HAS_QT_SOUND = True
except ImportError:
    HAS_QT_SOUND = False

# Folium
try:
    import folium
    from folium.plugins import MarkerCluster, HeatMap
    HAS_FOLIUM = True
except Exception:
    HAS_FOLIUM = False

# Matplotlib
try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ReportLab
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# ------------------------
# Ayarlar / Dosya yolları
# ------------------------
APP_DIR = os.path.abspath(os.path.dirname(__file__)) if "__file__" in globals() else os.getcwd()
DB_PATH = os.path.join(APP_DIR, "deprem.db")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
LOG_FILE = os.path.join(APP_DIR, "app.log")
SOUND_FILE = os.path.join(APP_DIR, "new_earthquake.wav")

DEFAULT_SETTINGS = {
    "theme": "dark",
    "mag_threshold_for_notification": 5.5,
    "auto_refresh_minutes": 5,
    "map_min_mag": 0.0
}

API_HEADERS = {"User-Agent": "DepremTakipApp/1.0 (Python PySide6)"}
API_LIVE = "https://api.orhanaydogdu.com.tr/deprem/kandilli/live"
API_ARCHIVE = "https://api.orhanaydogdu.com.tr/deprem/kandilli/archive"

# ------------------------
# Logging
# ------------------------
logger = logging.getLogger("deprem_app")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)

# ------------------------
# Yardımcı fonksiyonlar
# ------------------------
def load_settings() -> Dict[str, Any]:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
                d = DEFAULT_SETTINGS.copy(); d.update(s); return d
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(s: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def api_get(url: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    try:
        r = requests.get(url, params=params, headers=API_HEADERS, timeout=20)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, dict) and "result" in js and isinstance(js["result"], list):
            return js["result"]
        if isinstance(js, list):
            return js
    except Exception as ex:
        logger.info(f"API error {url}: {ex}")
    return []

def fetch_live_earthquakes() -> List[Dict[str, Any]]:
    return api_get(API_LIVE)

def fetch_archive_earthquakes(date_yyyy_mm_dd: str) -> List[Dict[str, Any]]:
    return api_get(API_ARCHIVE, params={"date": date_yyyy_mm_dd})

def mag_to_color(m: float) -> str:
    if m >= 7: return "darkred"
    if m >= 6: return "red"
    if m >= 5: return "orange"
    if m >= 4: return "yellow"
    if m >= 3: return "lightgreen"
    return "blue"

def play_sound_effect(sound_file):
    if not HAS_QT_SOUND:
        logger.warning("QSoundEffect kütüphanesi bulunamadı.")
        return
    if not os.path.exists(sound_file):
        logger.warning(f"Ses dosyası bulunamadı: {sound_file}")
        return
    
    try:
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(sound_file))
        effect.setLoopCount(1)
        effect.setVolume(1.0)
        effect.play()
    except Exception as ex:
        logger.error(f"Ses çalınırken hata oluştu: {ex}")

# ------------------------
# SQLite
# ------------------------
def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS earthquakes(
            earthquake_id TEXT PRIMARY KEY,
            provider TEXT,
            title TEXT,
            date TEXT,
            mag REAL,
            depth REAL,
            lon REAL,
            lat REAL,
            created_at INTEGER,
            closestCity_name TEXT,
            closestCity_code INTEGER,
            closestCity_distance REAL,
            closestCity_population INTEGER,
            epiCenter_name TEXT,
            airports_json TEXT
        )
    """)
    con.commit()
    con.close()

def db_upsert_earthquakes(items: List[Dict[str, Any]]):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    for e in items:
        try:
            gid = e.get("earthquake_id") or ""
            prov = e.get("provider") or ""
            title = e.get("title") or ""
            date = e.get("date") or e.get("date_time") or ""
            mag = float(e.get("mag") or 0)
            depth = float(e.get("depth") or 0)
            geo = e.get("geojson", {}).get("coordinates", [0,0])
            lon = float(geo[0]) if len(geo)>0 else 0.0
            lat = float(geo[1]) if len(geo)>1 else 0.0
            created_at = int(e.get("created_at") or int(time.time()))
            lp = e.get("location_properties", {}) or {}
            cc = lp.get("closestCity", {}) or {}
            cc_name = cc.get("name")
            cc_code = cc.get("cityCode")
            cc_dist = cc.get("distance")
            cc_pop = cc.get("population")
            epi = lp.get("epiCenter", {}) or {}
            epi_name = epi.get("name")
            airports = lp.get("airports", []) or []
            airports_json = json.dumps(airports, ensure_ascii=False)
            cur.execute("""
                INSERT INTO earthquakes
                (earthquake_id, provider, title, date, mag, depth, lon, lat, created_at,
                 closestCity_name, closestCity_code, closestCity_distance, closestCity_population,
                 epiCenter_name, airports_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(earthquake_id) DO UPDATE SET
                  provider=excluded.provider,
                  title=excluded.title,
                  date=excluded.date,
                  mag=excluded.mag,
                  depth=excluded.depth,
                  lon=excluded.lon,
                  lat=excluded.lat,
                  created_at=excluded.created_at,
                  closestCity_name=excluded.closestCity_name,
                  closestCity_code=excluded.closestCity_code,
                  closestCity_distance=excluded.closestCity_distance,
                  closestCity_population=excluded.closestCity_population,
                  epiCenter_name=excluded.epiCenter_name,
                  airports_json=excluded.airports_json
            """, (gid, prov, title, date, mag, depth, lon, lat, created_at,
                  cc_name, cc_code, cc_dist, cc_pop, epi_name, airports_json))
        except Exception as ex:
            logger.info(f"DB upsert error: {ex}")
    con.commit(); con.close()

def db_fetch_last(limit: int = 200) -> List[Dict[str, Any]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM earthquakes ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

# ------------------------
# UI bileşenleri
# ------------------------
class LogsTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        self.txt = QPlainTextEdit(); self.txt.setReadOnly(True); v.addWidget(self.txt)
        btn_row = QHBoxLayout(); clear_btn = QPushButton("Logları Temizle"); clear_btn.clicked.connect(self.txt.clear)
        btn_row.addWidget(clear_btn); btn_row.addStretch(1); v.addLayout(btn_row)
        
    def append(self, s: str): self.txt.appendPlainText(s)

class HomeTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.addWidget(QLabel("<h2>Deprem Gözlem'e Hoş Geldiniz</h2>"))
        self.lbl_last = QLabel("En son deprem: —"); self.lbl_stats = QLabel("Toplam: 0 | Ortalama M: — | En büyük: —")
        v.addWidget(self.lbl_last); v.addWidget(self.lbl_stats); v.addStretch(1)
    def update_overview(self, eqs: List[Dict[str, Any]]):
        if not eqs:
            self.lbl_last.setText("En son deprem: —"); self.lbl_stats.setText("Toplam: 0 | Ortalama M: — | En büyük: —"); return
        e0 = eqs[0]; self.lbl_last.setText(f"En son deprem: M{float(e0.get('mag') or 0):.1f} — {e0.get('title','')}\n{e0.get('date','')}")
        mags = [float(e.get("mag") or 0) for e in eqs]; avg = sum(mags)/len(mags) if mags else 0
        emax = max(eqs, key=lambda x: float(x.get("mag") or 0))
        self.lbl_stats.setText(f"Toplam: {len(eqs)} | Ortalama M: {avg:.2f} | En büyük: M{float(emax.get('mag') or 0):.1f} ({emax.get('title','')})")

class MapGeneratorWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, mode, date_str, min_mag, cluster_mode, tiles_url):
        super().__init__()
        self.mode = mode
        self.date_str = date_str
        self.min_mag = min_mag
        self.cluster_mode = cluster_mode
        self.tiles_url = tiles_url

    def run(self):
        if not HAS_FOLIUM:
            self.error.emit("Folium kütüphanesi bulunamadı.")
            return
        
        try:
            if self.mode == "Canlı Veri":
                eqs = fetch_live_earthquakes()
            else:
                eqs = fetch_archive_earthquakes(self.date_str)
            
            db_upsert_earthquakes(eqs)
            
            eqs_f = [e for e in eqs if float(e.get("mag") or 0) >= self.min_mag]
            
            attr = None
            tiles_to_use = self.tiles_url
            if tiles_to_use == "Esri Dünya Uydu":
                tiles_to_use = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                attr = "Tiles © Esri"

            if eqs_f:
                first = eqs_f[0]; coords = first.get("geojson", {}).get("coordinates", [35.0,39.0])
                lon = float(coords[0]); lat = float(coords[1]); m = folium.Map(location=[lat,lon], zoom_start=6, tiles=tiles_to_use, attr=attr)
            else:
                m = folium.Map(location=[39.0,35.0], zoom_start=6, tiles=tiles_to_use, attr=attr)

            if self.cluster_mode == "MarkerCluster":
                mc = MarkerCluster(); m.add_child(mc)
                for e in eqs_f:
                    coords = e.get("geojson", {}).get("coordinates", [0,0]); lon, lat = float(coords[0]), float(coords[1])
                    color = mag_to_color(float(e.get("mag") or 0))
                    popup_html = f"""
                        <b>Büyüklük:</b> M{float(e.get('mag') or 0):.1f}<br>
                        <b>Konum:</b> {e.get('title','')}<br>
                        <b>Tarih:</b> {e.get('date','')}<br>
                        <b>Derinlik:</b> {float(e.get('depth') or 0):.1f} km
                    """
                    popup = folium.Popup(popup_html, max_width=300)
                    folium.CircleMarker(location=[lat,lon], radius=max(4,float(e.get('mag') or 0)*1.5),
                                        color=color, fill=True, fill_opacity=0.7, popup=popup, tooltip=popup_html).add_to(mc)
            elif self.cluster_mode == "HeatMap":
                heat = []
                for e in eqs_f:
                    coords = e.get("geojson", {}).get("coordinates", [0,0]); lon, lat = float(coords[0]), float(coords[1])
                    heat.append([lat, lon, float(e.get("mag") or 0)])
                if heat: HeatMap(heat, radius=18).add_to(m)
            else:
                for e in eqs_f:
                    coords = e.get("geojson", {}).get("coordinates", [0,0]); lon, lat = float(coords[0]), float(coords[1])
                    color = mag_to_color(float(e.get("mag") or 0))
                    popup_html = f"""
                        <b>Büyüklük:</b> M{float(e.get('mag') or 0):.1f}<br>
                        <b>Konum:</b> {e.get('title','')}<br>
                        <b>Tarih:</b> {e.get('date','')}<br>
                        <b>Derinlik:</b> {float(e.get('depth') or 0):.1f} km
                    """
                    popup = folium.Popup(popup_html, max_width=300)
                    folium.CircleMarker(location=[lat,lon], radius=max(4,float(e.get('mag') or 0)*1.5),
                                        color=color, fill=True, fill_opacity=0.7, popup=popup, tooltip=popup_html).add_to(m)
            
            folium.LayerControl().add_to(m)
            fd, path = tempfile.mkstemp(suffix=".html"); os.close(fd)
            m.save(path)
            self.finished.emit(path)

        except Exception as ex:
            self.error.emit(f"Harita oluşturma hatası: {ex}")

class MapTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        ctl = QHBoxLayout()
        self.mode = QComboBox(); self.mode.addItems(["Canlı Veri", "Arşiv (Tarih Seç)"])
        self.date = QDateEdit(); self.date.setCalendarPopup(True); self.date.setDate(QDate.currentDate()); self.date.setVisible(False)
        self.min_mag = QDoubleSpinBox(); self.min_mag.setRange(0,10); self.min_mag.setSingleStep(0.1); self.min_mag.setValue(load_settings().get("map_min_mag",0.0))
        self.cluster = QComboBox(); self.cluster.addItems(["Yok","MarkerCluster","HeatMap"])
        self.tiles = QComboBox(); self.tiles.addItems(["OpenStreetMap"])
        btn = QPushButton("Haritayı Yenile"); btn.clicked.connect(self.refresh)
        ctl.addWidget(QLabel("Mod:")); ctl.addWidget(self.mode); ctl.addWidget(self.date)
        ctl.addWidget(QLabel("Min M:")); ctl.addWidget(self.min_mag); ctl.addWidget(QLabel("Küme:")); ctl.addWidget(self.cluster)
        ctl.addWidget(QLabel("Katman:")); ctl.addWidget(self.tiles); ctl.addWidget(btn); ctl.addStretch(1)
        v.addLayout(ctl)

        self.loading_label = QLabel("Harita Yükleniyor...");
        self.loading_label.setAlignment(Qt.AlignCenter);
        self.loading_label.setVisible(False);
        v.addWidget(self.loading_label)

        if HAS_WEBENGINE:
            self.view = QWebEngineView()
            s = self.view.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            v.addWidget(self.view)
        else:
            self.view = None; v.addWidget(QLabel("QWebEngine bulunamadı. Harita devre dışı."))
        
        self.thread = None
        self.worker = None

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.tiles.currentIndexChanged.connect(self.refresh)
        self.min_mag.valueChanged.connect(self.refresh)
        self.cluster.currentIndexChanged.connect(self.refresh)
        self._last_eqs: List[Dict[str, Any]] = []

    def _mode_changed(self, ix: int): 
        self.date.setVisible(ix==1)
        self.refresh()

    def set_data(self, eqs: List[Dict[str, Any]]):
        self._last_eqs = eqs
        self.refresh()
    
    def refresh(self):
        if self.thread is not None and self.thread.isRunning():
            return
        
        self.loading_label.setVisible(True)
        if self.view:
            self.view.setVisible(False)
        
        self.thread = QThread()
        self.worker = MapGeneratorWorker(
            mode=self.mode.currentText(),
            date_str=self.date.date().toString("yyyy-MM-dd"),
            min_mag=self.min_mag.value(),
            cluster_mode=self.cluster.currentText(),
            tiles_url=self.tiles.currentText()
        )
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_map_generated)
        self.worker.error.connect(self._on_map_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        
        self.thread.finished.connect(self._on_thread_finished)
        
        self.thread.start()

    def _on_map_generated(self, path: str):
        if path and self.view:
            self.view.load(QUrl.fromLocalFile(path))
            self.loading_label.setVisible(False)
            self.view.setVisible(True)
        else:
            self.loading_label.setText("Harita yüklenemedi.")
        
    def _on_map_error(self, message: str):
        self.loading_label.setText(f"Harita hatası: {message}")
        
    def _on_thread_finished(self):
        if self.thread:
            self.thread.deleteLater()
            self.thread = None
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def focus_on(self, lat: float, lon: float, mag: float = 4.0, title: str = ""):
        if not HAS_FOLIUM or not self.view: return
        try:
            m = folium.Map(location=[lat, lon], zoom_start=9, tiles="OpenStreetMap")
            popup_html = f"""
                <b>Büyüklük:</b> M{mag:.1f}<br>
                <b>Konum:</b> {title}<br>
            """
            popup = folium.Popup(popup_html, max_width=300)
            folium.CircleMarker([lat,lon], radius=max(6, mag*2), color=mag_to_color(mag), fill=True, popup=popup, tooltip=popup_html).add_to(m)
            fd, path = tempfile.mkstemp(suffix=".html"); os.close(fd)
            m.save(path); self.view.load(QUrl.fromLocalFile(path))
        except Exception as ex:
            logger.info(f"Map focus error: {ex}")

class NearTab(QWidget):
    def __init__(self, on_row_focus=None):
        super().__init__()
        self.on_row_focus = on_row_focus
        v = QVBoxLayout(self)

        self.deprem_model = QStandardItemModel()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.deprem_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        
        self.deprem_table = QTableView()
        self.deprem_table.setModel(self.proxy_model)
        self.deprem_table.setSortingEnabled(True)
        self.deprem_table.setWordWrap(True)
        self.deprem_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.deprem_table.horizontalHeader().setStretchLastSection(True)
        self.deprem_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.deprem_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        
        v.addWidget(self.deprem_table)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Son 200 Depremi Getir"); self.btn_refresh.clicked.connect(self.refresh_data)
        self.btn_csv = QPushButton("CSV Dışa Aktar"); self.btn_csv.clicked.connect(self.export_csv)
        self.btn_pdf = QPushButton("PDF Dışa Aktar"); self.btn_pdf.clicked.connect(self.export_pdf)
        row.addWidget(self.btn_refresh); row.addWidget(self.btn_csv); row.addWidget(self.btn_pdf); row.addStretch(1)
        v.addLayout(row)

        self.deprem_table.clicked.connect(self._clicked)
        self._last_data: List[Dict[str, Any]] = []

    def _clicked(self, index):
        row = self.proxy_model.mapToSource(index).row()
        try:
            e = self._last_data[row]
            # HATA DÜZELTİLMİŞ SATIRLAR: lon ve lat değerlerini doğrudan sözlükten alıyor
            lon = float(e.get("lon", 0.0))
            lat = float(e.get("lat", 0.0))
            mag = float(e.get("mag") or 0)
            title = e.get("title", "")
            if self.on_row_focus:
                self.on_row_focus(lat, lon, mag, title)
        except Exception as ex:
            logger.info(f"NearTab click error: {ex}")

    def refresh_data(self):
        rows = db_fetch_last(200)
        
        if not rows:
            eqs = fetch_live_earthquakes()
            db_upsert_earthquakes(eqs)
            rows = db_fetch_last(200)
        
        self._last_data = rows
        self.deprem_model.clear()
        
        headers = [
            "Tarih", "Yer", "Büyüklük", "Derinlik (km)", "En Yakın Şehir",
            "En Yakın Şehir Kodu", "En Yakın Şehir Uzaklık (km)", "Şehir Nüfusu",
            "Epi Center", "Havalimanları", "Uzaklıklar (km)"
        ]
        self.deprem_model.setHorizontalHeaderLabels(headers)

        for e in rows:
            lp = e.get("location_properties", {}) or {}
            cc = lp.get("closestCity", {}) or {}
            airports = e.get("airports_json", "[]") 
            airports = json.loads(airports) if airports else []

            airports_names = "\n".join([a.get("name","") for a in airports]) if airports else "-"
            dists = []
            for a in airports:
                try: dkm = int(float(a.get("distance",0))/1000)
                except: dkm = 0
                dists.append(str(dkm))
            airports_dists = "\n".join(dists) if dists else "-"

            row_items = [
                QStandardItem(str(e.get("date",""))),
                QStandardItem(str(e.get("title",""))),
                QStandardItem(f"{float(e.get('mag') or 0):.1f}"),
                QStandardItem(f"{float(e.get('depth') or 0):.1f}"),
                QStandardItem(str(cc.get("name",""))),
                QStandardItem(str(cc.get("cityCode",""))),
                QStandardItem(f"{float(cc.get('distance',0)/1000):.1f}"),
                QStandardItem(str(cc.get("population",""))),
                QStandardItem((lp.get("epiCenter", {}) or {}).get("name","")),
                QStandardItem(airports_names),
                QStandardItem(airports_dists)
            ]
            self.deprem_model.appendRow(row_items)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "CSV Kaydet", os.path.expanduser("~"), "CSV Files (*.csv)")
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                headers = [self.deprem_model.headerData(i, Qt.Horizontal) for i in range(self.deprem_model.columnCount())]
                w.writerow(headers)
                for r in range(self.deprem_model.rowCount()):
                    row = [self.deprem_model.item(r,c).text() if self.deprem_model.item(r,c) else "" for c in range(self.deprem_model.columnCount())]
                    w.writerow(row)
            QMessageBox.information(self, "Tamam", f"CSV kaydedildi: {path}")
        except Exception as ex:
            QMessageBox.critical(self, "Hata", f"CSV kaydedilemedi: {ex}")

    def export_pdf(self):
        if not HAS_REPORTLAB:
            QMessageBox.warning(self, "Uyarı", "PDF oluşturmak için reportlab gerekli (pip install reportlab)."); return
        path, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", os.path.expanduser("~"), "PDF Files (*.pdf)")
        if not path: return
        try:
            doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
            story = []
            styles = getSampleStyleSheet()
            
            title_style = styles["h2"]
            title_style.alignment = 1 
            story.append(Paragraph("Yakındaki Depremler Raporu", title_style))
            story.append(Spacer(1, 12))
            
            headers = [self.deprem_model.headerData(i, Qt.Horizontal) for i in range(self.deprem_model.columnCount())]
            data = [headers]
            for r in range(self.deprem_model.rowCount()):
                row_data = [self.deprem_model.item(r,c).text() if self.deprem_model.item(r,c) else "" for c in range(self.deprem_model.columnCount())]
                data.append(row_data)

            if len(data) > 1:
                table_style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTSIZE', (0, 1), (-1, -1), 7),
                ])
                t = Table(data)
                t.setStyle(table_style)
                story.append(t)

            doc.build(story)
            QMessageBox.information(self, "Tamam", f"PDF kaydedildi: {path}")
        except Exception as ex:
            QMessageBox.critical(self, "Hata", f"PDF kaydedilemedi: {ex}")

class AnalysisTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self); ctl = QHBoxLayout()
        self.combo = QComboBox(); 
        self.combo.addItems(["Büyüklük - Zaman","Büyüklük Dağılımı","Derinlik Dağılımı","Günlük Ortalama Büyüklük"])
        ctl.addWidget(QLabel("Analiz:")); ctl.addWidget(self.combo); ctl.addStretch(1); v.addLayout(ctl)
        if HAS_MATPLOTLIB:
            self.fig = Figure(figsize=(6,3)); self.canvas = FigureCanvas(self.fig); self.toolbar = NavigationToolbar(self.canvas,self)
            v.addWidget(self.toolbar); v.addWidget(self.canvas)
        else:
            self.fig, self.canvas = None, None
            v.addWidget(QLabel("Matplotlib bulunamadı. Grafik devre dışı."))

        self._data: List[Dict[str, Any]] = []
        if HAS_MATPLOTLIB: self.combo.currentIndexChanged.connect(self._replot)
        self.premium_options = ["Deprem Tahmin Trendleri", "1 Haftalık Geçmiş"]
        
    def set_data(self, eqs: List[Dict[str, Any]]): self._data = eqs; self._replot()
    
    def _replot(self):
        if not HAS_MATPLOTLIB or not self.fig: return
        self.fig.clear(); ax = self.fig.add_subplot(111)
        eqs = self._data
        if not eqs: ax.text(0.5,0.5,"Veri yok", ha="center"); self.canvas.draw_idle(); return
        try:
            if self.combo.currentText() == "Büyüklük - Zaman":
                xs = [int(e.get("created_at") or 0) for e in eqs]; ys = [float(e.get("mag") or 0) for e in eqs]; ax.plot(xs,ys,marker="o",linestyle="-"); ax.set_xlabel("Zaman (Unix)"); ax.set_ylabel("M")
            elif self.combo.currentText() == "Büyüklük Dağılımı":
                mags=[float(e.get("mag") or 0) for e in eqs]; ax.hist(mags,bins=20); ax.set_xlabel("M"); ax.set_ylabel("Frekans")
            elif self.combo.currentText() == "Derinlik Dağılımı":
                depths=[float(e.get("depth") or 0) for e in eqs]; ax.hist(depths,bins=20); ax.set_xlabel("Derinlik (km)"); ax.set_ylabel("Frekans")
            elif self.combo.currentText() == "Günlük Ortalama Büyüklük":
                from collections import defaultdict; buckets=defaultdict(list); import datetime as _dt
                for e in eqs:
                    ts = int(e.get("created_at") or 0); day = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d"); buckets[day].append(float(e.get("mag") or 0))
                days = sorted(buckets.keys()); avgs = [sum(buckets[d])/len(buckets[d]) for d in days]; ax.plot(days,avgs,marker="o"); ax.set_xlabel("Gün"); ax.set_ylabel("Ortalama M"); ax.tick_params(axis='x', rotation=45)
        except Exception as ex:
            logger.info(f"Plot error: {ex}"); ax.text(0.5,0.5,"Grafik hatası", ha="center")
        self.canvas.draw_idle()

class RiskTab(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self); v.addWidget(QLabel("<h3>Bina Riski Analizi (Basit)</h3>"))
        form = QFormLayout(); self.year=QSpinBox(); self.year.setRange(1900,2100); self.year.setValue(2000)
        self.floors=QSpinBox(); self.floors.setRange(1,50); self.floors.setValue(5)
        self.quality=QComboBox(); self.quality.addItems(["Yetersiz","Orta","İyi"])
        self.btn = QPushButton("Riski Hesapla"); self.res = QLabel("—"); form.addRow("Yapım Yılı:", self.year); form.addRow("Kat Sayısı:", self.floors); form.addRow("İnşaat Kalitesi:", self.quality); form.addRow(self.btn); form.addRow("Sonuç:", self.res)
        v.addLayout(form); v.addStretch(1); self.btn.clicked.connect(self._calc)
        
    def _calc(self):
        y=self.year.value(); f=self.floors.value(); q=self.quality.currentText(); risk=0; risk += 5 if y<1980 else (3 if y<2000 else 1); risk += f*0.4; risk += {"Yetersiz":4,"Orta":2,"İyi":0}[q]
        
        if risk>=10: txt="<b><font color='red'>YÜKSEK</font></b>"
        elif risk>=6: txt="<b><font color='orange'>ORTA</font></b>"
        else: txt="<b><font color='green'>DÜŞÜK</font></b>"
        self.res.setText(f"{txt} risk (puan: {risk:.1f}) — Bu yalnızca basit bir tahmindir.")
        
class InfoTab(QWidget):
    def __init__(self):
        super().__init__(); v=QVBoxLayout(self); v.addWidget(QLabel("<h3>Bilgi Merkezi</h3>"))
        text = ("Deprem Öncesi:\n- Acil çanta...\n\nDeprem Anında:\n- Çök-Kapan-Tutun...\n\nDeprem Sonrası:\n- Yetkilileri takip edin...")
        t = QPlainTextEdit(text); t.setReadOnly(True); v.addWidget(t); v.addStretch(1)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deprem Gözlem")
        self.setWindowIcon(QIcon.fromTheme("applications-system"))
        self.settings = load_settings()
        db_init()
        splitter = QSplitter(); left = QWidget(); left_v = QVBoxLayout(left); self.tabs = QTabWidget(); left_v.addWidget(self.tabs); splitter.addWidget(left)
        right = QWidget(); right_v = QVBoxLayout(right); self.lbl_quick = QLabel("<b>Hızlı İstatistik</b><br>—"); self.btn_refresh_all = QPushButton("Tümünü Yenile"); self.btn_refresh_all.clicked.connect(self.refresh_all)
        right_v.addWidget(self.lbl_quick); right_v.addWidget(self.btn_refresh_all); right_v.addStretch(1); splitter.addWidget(right); splitter.setSizes([1100,300]); self.setCentralWidget(splitter)
        
        self.home_tab = HomeTab()
        self.map_tab = MapTab()
        self.near_tab = NearTab(on_row_focus=self.show_map_with_focus)
        self.analysis_tab = AnalysisTab()
        self.risk_tab = RiskTab()
        self.info_tab = InfoTab()
        self.logs_tab = LogsTab()
        
        self.tabs.addTab(self.home_tab,"Ana Sayfa")
        self.tabs.addTab(self.map_tab,"Harita")
        self.tabs.addTab(self.near_tab,"Yakındaki Depremler")
        self.tabs.addTab(self.analysis_tab,"Analizler")
        self.tabs.addTab(self.risk_tab,"Bina Riski Analizi")
        self.tabs.addTab(self.info_tab,"Bilgi Merkezi")
        self.tabs.addTab(self.logs_tab,"Loglar")
        
        self._setup_menu()
        self.tray = QSystemTrayIcon(QIcon.fromTheme("dialog-information"), self); tray_menu = QMenu(); act_show = QAction("Göster", self); act_show.triggered.connect(lambda: (self.showNormal(), self.raise_())); act_quit = QAction("Çıkış", self); act_quit.triggered.connect(self.close); tray_menu.addAction(act_show); tray_menu.addAction(act_quit); self.tray.setContextMenu(tray_menu); self.tray.show()
        self.apply_theme(self.settings.get("theme","dark"))
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh_all); self.timer.setInterval(max(1,int(self.settings.get("auto_refresh_minutes",5)))*60*1000)
        
        self.refresh_all()

    def _setup_menu(self):
        menubar = self.menuBar(); m_file = menubar.addMenu("&Dosya"); act_refresh = QAction("Yenile", self); act_refresh.triggered.connect(self.refresh_all); act_exit = QAction("Çıkış", self); act_exit.triggered.connect(self.close); m_file.addAction(act_refresh); m_file.addSeparator(); m_file.addAction(act_exit)
        m_view = menubar.addMenu("&Görünüm"); act_dark = QAction("Koyu Tema", self); act_dark.triggered.connect(lambda: self.apply_theme("dark")); act_light = QAction("Açık Tema", self); act_light.triggered.connect(lambda: self.apply_theme("light")); m_view.addAction(act_dark); m_view.addAction(act_light)
    
    def show_map_with_focus(self, lat: float, lon: float, mag: float, title: str):
        """Harita sekmesini açar ve haritayı belirtilen konuma odaklama işlemi yapar."""
        self.map_tab.focus_on(lat, lon, mag, title)
        self.tabs.setCurrentWidget(self.map_tab)
        
    def apply_theme(self, theme: str):
        if theme == "light": self.setStyleSheet("")
        else:
            self.setStyleSheet("QWidget{background:#2b2b2b;color:#e6e6e6;} QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTableWidget{background:#3c3f41;color:#fff;} QPushButton{background:#3c3f41;color:#fff;padding:6px;border:1px solid #555;}")
        self.settings["theme"] = theme; save_settings(self.settings)

    def refresh_all(self):
        try:
            live = fetch_live_earthquakes()
            if live:
                db_upsert_earthquakes(live)
                try: th = float(self.settings.get("mag_threshold_for_notification",5.5))
                except: th = 5.5
                top = live[0]
                if float(top.get("mag") or 0) >= th: 
                    self.tray.showMessage("Yeni Deprem", f"M{float(top.get('mag') or 0):.1f} — {top.get('title','')}", QSystemTrayIcon.Information)
            
            rows = db_fetch_last(200)
            
            self.home_tab.update_overview(rows)
            self.map_tab.set_data(rows)
            self.near_tab.refresh_data()
            self.analysis_tab.set_data(rows)
            
            mags = [float(e.get("mag") or 0) for e in rows]; txt = f"Son {len(rows)} deprem | Ortalama M: {(sum(mags)/len(mags)):.2f}" if mags else "—"
            self.lbl_quick.setText(f"<b>Hızlı İstatistik</b><br>{txt}")
            self.logs_tab.append(f"Yenilendi: {len(rows)} kayıt")
            
        except Exception as ex:
            logger.info(f"refresh_all error: {ex}"); self.logs_tab.append(f"Hata: {ex}")

# ------------------------
# Entry
# ------------------------
def main():
    app = QApplication(sys.argv)
    if not QIcon.themeName(): QIcon.setThemeName("breeze")
    w = MainWindow(); w.resize(1280,820); w.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()