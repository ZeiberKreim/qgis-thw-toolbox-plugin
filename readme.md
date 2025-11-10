# THW Toolbox Plugin

![Plugin-Vorschau](https://thw-minden.de/qgis-plugin/preview.gif)

Ein QGIS-Plugin für das einfache Hinzufügen und Verwalten von taktischen Zeichen auf der Karte. Entwickelt speziell für den Einsatz im Technischen Hilfswerk (THW) und anderen Einsatzorganisationen.

## 🚀 Schnellstart

1. **Plugin aktivieren**: Klicken Sie auf das THW Toolbox-Symbol in der QGIS-Toolbar
2. **Symbol auswählen**: Wählen Sie ein Symbol aus dem Dock aus
3. **Platzieren**: Ziehen Sie das Symbol auf die Karte oder klicken Sie auf die gewünschte Position
4. **Bearbeiten**: Klicken Sie auf ein Symbol, um es zu verschieben, zu skalieren oder zu beschriften

## ✨ Hauptfunktionen

### 🎯 Intuitive Symbol-Platzierung
- **Drag & Drop**: Ziehen Sie Symbole direkt aus dem Dock auf die Karte
- **Klick-Modus**: Wählen Sie ein Symbol und klicken Sie auf die gewünschte Position
- **Intelligente Größenanpassung**: Symbole werden automatisch an den aktuellen Zoom-Faktor angepasst
- **Persistente Speicherung**: Alle Symbole werden automatisch in einer GeoPackage-Datei gespeichert

### 🔍 Umfassendes Feature-Management
- **Identifizierung**: Klicken Sie auf Symbole, um Details anzuzeigen
- **Verschieben**: Symbole können einfach mit der Maus verschoben werden
- **Größenanpassung**: Dynamische Größenänderung mit Schieberegler
- **Labeling**: Beschriftung der Symbole mit anpassbarem Text und Positionierung
- **Echtzeit-Vorschau**: Sofortige visuelle Rückmeldung bei Änderungen

### 📁 Umfangreiche Symbol-Bibliothek
Das Plugin enthält eine umfassende Sammlung von taktischen Zeichen für:

- **THW** (Technisches Hilfswerk) - Einheiten, Fahrzeuge, Personen, Gebäude
- **Bundeswehr** - Einheiten, Fahrzeuge, Personen
- **Feuerwehr** - Einheiten, Fahrzeuge, Personen, Gebäude
- **Polizei** - Einheiten und Fahrzeuge
- **Rettungswesen** - Einheiten, Fahrzeuge, Personen, Einrichtungen
- **Katastrophenschutz** - Einheiten und Fahrzeuge
- **Wasserrettung** - Einheiten, Fahrzeuge, Personen, Einrichtungen
- **Zoll** - Einheiten und Fahrzeuge
- **Einrichtungen** - Führungsstellen, Versorgungsstellen, Behandlungsplätze
- **Gefahren** - Verschiedene Gefahrensymbole
- **Maßnahmen** - Einsatzmaßnahmen und Aktionen
- **Schäden** - Schadensdarstellungen
- Und viele weitere Kategorien

### 💾 Intelligente Datenverwaltung
- **Automatisches Speichern**: Änderungen werden automatisch gespeichert
- **Projekt-Integration**: Layer-Dateien werden beim Speichern des Projekts verschoben
- **Portable Pakete**: Export-Funktion für vollständig portable Symbol-Sammlungen
- **SVG-Embedding**: Alle SVG-Inhalte werden in der GeoPackage gespeichert für maximale Portabilität

### 🔎 Schnelle Symbol-Suche
- **Echtzeit-Suche**: Sofortige Filterung beim Tippen
- **Mehrsprachig**: Suche funktioniert mit deutschen und englischen Begriffen
- **Kategorien-Filter**: Schnelle Navigation durch verschiedene Symbol-Kategorien

## 📦 Installation

### Voraussetzungen
- **QGIS**: Version 3.0 oder höher
- **Python**: Version 3.x (wird mit QGIS mitgeliefert)
- **Betriebssystem**: Windows, Linux oder macOS

### Installationsschritte

#### Option 1: Manuelle Installation
1. Laden Sie das Plugin herunter oder klonen Sie das Repository
2. Kopieren Sie den Plugin-Ordner in Ihr QGIS Plugin-Verzeichnis:
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - **Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **macOS**: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

3. Starten Sie QGIS neu oder laden Sie das Plugin über den Plugin-Manager

#### Option 2: Über den QGIS Plugin-Manager
1. Öffnen Sie QGIS
2. Gehen Sie zu `Plugins` → `Verwalten und installieren`
3. Klicken Sie auf den Tab "Installiert"
4. Aktivieren Sie "THW Toolbox" in der Liste

4. Das Plugin-Symbol erscheint in der QGIS-Toolbar

## 📖 Verwendung

### Plugin aktivieren
1. Klicken Sie auf das **THW Toolbox-Symbol** in der QGIS-Toolbar
2. Das **Symbol-Dock** öffnet sich rechts in QGIS
3. Ein neuer Layer **"THW Toolbox Marker"** wird automatisch erstellt

### Symbole platzieren

1. Navigieren Sie im Symbol-Dock zu der gewünschten Kategorie
2. Ziehen Sie ein Symbol aus dem Dock
3. Lassen Sie es auf der gewünschten Position auf der Karte los


### Symbole bearbeiten

#### Symbol identifizieren und auswählen
1. Klicken Sie auf ein Symbol auf der Karte
2. Das **Feature-Dock** öffnet sich und zeigt alle Eigenschaften des Symbols
3. Das ausgewählte Symbol wird hervorgehoben

#### Symbol verschieben
1. Wählen Sie ein Symbol aus (siehe oben)
2. Halten Sie die **linke Maustaste** gedrückt
3. Ziehen Sie das Symbol an die neue Position
4. Lassen Sie die Maustaste los

#### Symbolgröße ändern
1. Wählen Sie ein Symbol aus
2. Verwenden Sie den **Größen-Schieberegler** im Feature-Dock
3. Die Änderung wird sofort auf der Karte sichtbar

#### Label hinzufügen oder bearbeiten
1. Wählen Sie ein Symbol aus
2. Aktivieren Sie **"Label anzeigen"** im Feature-Dock
3. Geben Sie den gewünschten Text in das **Label-Feld** ein
4. Das Label wird automatisch unter dem Symbol angezeigt

### Symbol-Suche verwenden
- Verwenden Sie die **Suchleiste** im oberen Bereich des Symbol-Docks
- Die Suche filtert die Symbole in Echtzeit
- Die Suche funktioniert sowohl mit deutschen als auch englischen Begriffen
- Klicken Sie auf das **X** oder löschen Sie den Text, um die Suche zurückzusetzen

## 🔧 Technische Details

### Datenformat
- **Layer-Typ**: GeoPackage (.gpkg)
- **Geometrie**: Punkt-Features
- **Symbole**: SVG-Dateien mit eingebettetem Inhalt
- **Koordinatensystem**: Automatische Anpassung an das Projekt-CRS
- **Speicherort**: Temporäre Dateien werden im `tmp`-Verzeichnis des Plugins gespeichert

### Feature-Attribute
Jedes Symbol-Feature enthält folgende Attribute:

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| `name` | String | Name der SVG-Datei |
| `svg_path` | String | Relativer Pfad zur SVG-Datei |
| `svg_content` | String | Vollständiger SVG-Inhalt (für Portabilität) |
| `size` | Real | Symbolgröße in Map Units |
| `scale_with_map` | Boolean | Ob das Symbol mit der Karte skalieren soll |
| `unique_id` | String | Eindeutige Identifikation des Features |
| `label` | String | Beschriftungstext |
| `show_label` | Boolean | Ob die Beschriftung angezeigt werden soll |

### Performance-Optimierungen
- **Intelligente Toleranz**: Feature-Erkennung basiert auf Symbolgröße für präzise Auswahl
- **Throttling**: Aktualisierungen werden gedrosselt für bessere Performance bei vielen Features
- **Caching**: SVG-Icons werden gecacht für schnelle Anzeige im Dock
- **Lazy Loading**: Symbol-Ordner werden nur bei Bedarf geladen
- **Effiziente Rendering**: Optimierte SVG-Darstellung auf der Karte

## 📤 Export-Funktionen

### Portables Paket erstellen
Erstellen Sie ein vollständig portables Paket mit allen Symbolen und Daten:

1. Gehen Sie zu `Plugins` → `THW Toolbox` → `Portables Paket exportieren`
2. Wählen Sie einen Zielordner aus
3. Das Plugin erstellt automatisch ein ZIP-Archiv mit:
   - Allen SVG-Symbolen aus der Bibliothek
   - Der GeoPackage-Datei mit allen platzierten Symbolen
   - Installationsanweisungen
   - README-Datei

Das exportierte Paket kann auf anderen Systemen verwendet werden, ohne dass zusätzliche Abhängigkeiten erforderlich sind.

## 📄 Lizenzinformationen

### Externe Ressourcen

#### Taktische Zeichen
- **Lizenz**: CC BY 4.0 (Creative Commons Attribution 4.0 International)
- **Quelle**: [Taktische-Zeichen auf GitHub](https://github.com/jonas-koeritz/Taktische-Zeichen)
- **Verwendung**: Die SVG-Symbole werden unter der CC BY 4.0-Lizenz bereitgestellt

#### Google Roboto Font
- **Lizenz**: Apache 2.0 (Apache License, Version 2.0)
- **Quelle**: [Google Fonts - Roboto](https://fonts.google.com/specimen/Roboto)
- **Verwendung**: Wird für die Beschriftungen verwendet

### Plugin-Lizenz
Dieses Plugin steht unter der **MIT-Lizenz** zur Verfügung. Siehe die `LICENSE`-Datei im Repository für Details.

## 🆘 Support und Fehlerbehebung

### Häufige Probleme

#### Plugin erscheint nicht in der Toolbar
- Überprüfen Sie, ob das Plugin im Plugin-Manager aktiviert ist
- Starten Sie QGIS neu
- Überprüfen Sie die QGIS-Version (mindestens 3.0 erforderlich)

#### Symbole werden nicht angezeigt
- Überprüfen Sie, ob der Layer "THW Toolbox Marker" sichtbar ist
- Überprüfen Sie die Verfügbarkeit der SVG-Dateien im `svgs`-Verzeichnis
- Überprüfen Sie die Schreibrechte im Plugin-Verzeichnis

#### Performance-Probleme
- Reduzieren Sie die Anzahl der gleichzeitig angezeigten Symbole
- Überprüfen Sie die Größe der SVG-Dateien
- Schließen Sie andere große Projekte oder Layer

### Log-Dateien
Bei Problemen können Sie die Log-Datei überprüfen:
- **Log-Datei**: `svg_dock.log` im Plugin-Verzeichnis
- **QGIS-Log**: `Plugins` → `Python-Konsole` → Log-Ausgabe

### Bekannte Einschränkungen
- Symbole werden nur in Punkt-Layern unterstützt
- Sehr große SVG-Dateien (> 1 MB) können die Performance beeinträchtigen
- Bei sehr vielen Symbolen (> 1000) kann die Darstellung verlangsamt werden
- Die Symbol-Suche ist case-sensitive

## 📝 Changelog

### Version 0.1
- ✨ Erste Veröffentlichung
- 🎯 Grundlegende Drag & Drop-Funktionalität
- 🔍 Feature-Identifizierung und -Bearbeitung
- 📁 Umfangreiche Symbol-Bibliothek mit über 1000 Symbolen
- 💾 Export-Funktionen für portable Pakete
- 🔎 Symbol-Suche mit Mehrsprachigkeit
- 📝 Labeling-Funktionalität
- ⚡ Performance-Optimierungen

## 🤝 Beitragen

Verbesserungsvorschläge, Bug-Reports und Pull Requests sind herzlich willkommen!

### Wie Sie beitragen können
- 🐛 **Bug-Reports**: Melden Sie Fehler über GitHub Issues
- 💡 **Feature-Vorschläge**: Teilen Sie Ihre Ideen mit
- 📝 **Dokumentation**: Helfen Sie bei der Verbesserung der Dokumentation
- 🔧 **Code-Beiträge**: Pull Requests sind willkommen

---

**Hinweis**: Dieses Plugin wurde für den Einsatz im Technischen Hilfswerk (THW) entwickelt, kann aber auch für andere Organisationen und Zwecke verwendet werden. Die taktischen Zeichen entsprechen den offiziellen Standards und können in verschiedenen Einsatzszenarien verwendet werden.
