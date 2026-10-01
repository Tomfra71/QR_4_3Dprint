# Generator zawieszek QR (Bambu Lab P2S)

Tworzy plik `.3mf` z partią zawieszek: QR na górze, numer (lustrzany) na spodzie.
Każda zawieszka jest osobnym obiektem, więc w trakcie wydruku można pominąć
uszkodzoną sztukę („Skip objects”).

## Instalacja (jednorazowo)

Potrzebny Python 3.10 lub nowszy (https://www.python.org/downloads/ –
przy instalacji na Windows zaznacz „Add python.exe to PATH”).

W folderze z plikami otwórz terminal (Windows: w Eksploratorze wpisz `cmd`
w pasku adresu i Enter) i wpisz:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Na Linux/macOS zamiast drugiej linii: `source .venv/bin/activate`.

## Uruchomienie

1. Otwórz `BEgenerator.py` w edytorze i ustaw partię na początku pliku:
   `NUMER_STARTOWY` i `ILE_SZTUK` (maks. 60 na stole).
2. W terminalu (w tym samym folderze):

   ```
   .venv\Scripts\activate
   python BEgenerator.py
   ```

3. Powstanie plik `Zawieszki_BE....3mf` – otwórz go w Bambu Studio
   i postępuj według instrukcji wypisanej przez skrypt.
