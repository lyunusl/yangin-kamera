@echo off
rem Tek dosyalik YanginKamera exe'sini derler (hedef bilgisayarda Python ya da kurulum gerekmez).
rem   kurulum\derle.cmd            Community paketi: dist\community\YanginKamera-community.exe
rem   kurulum\derle.cmd duz        duz modelle (gelistirme): dist\YanginKamera.exe
rem Inno Setup 6 kuruluysa ayrica kurulum dosyasi: dist\kurulum\YanginKamera-Kurulum-0.1.0.exe
setlocal
cd /d "%~dp0.."

set KIP=%~1
if "%KIP%"=="" set KIP=community

if not exist .venv\Scripts\python.exe (
  py -3.12 -m venv .venv || goto :hata
  .venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller==6.19.0 || goto :hata
)
if not exist motor\deps\onnxruntime\__init__.py (
  echo motor\deps hazir degil: README'deki kaynak kod kurulumu bolumune bakin.
  goto :hata
)
if /i "%KIP%"=="community" if not exist kurulum\community-modeller\community-paket.json (
  echo Community model paketi bulunamadi: kurulum\community-modeller
  goto :hata
)

rem Gelistirme sinamalari yalnizca egitim\ klasoru olan kopyada calisir (GitHub'daki kopyada yoktur).
for %%S in (dene_kurulum dene_motor_yerlesimi dene_arayuzsuz dene_model_lisansi dene_kurallar) do (
  if exist egitim\%%S.py (
    .venv\Scripts\python egitim\%%S.py >nul 2>&1 || (echo %%S basarisiz & goto :hata)
  )
)
if not exist kurulum\sahne\yangin-kamera.pmod (
  echo Hazir sahne yok: kurulum\sahne\yangin-kamera.pmod
  echo README'deki adimlarla bir kez uretin: kurulum\sablon.py, sonra Studio'da Farkli Kaydet.
  goto :hata
)
.venv\Scripts\python kurulum\simge.py >nul || goto :hata

if /i "%KIP%"=="duz" (
  set YANGIN_MODEL_PAKETI=
  .venv\Scripts\python -m PyInstaller kurulum\YanginKamera.spec --noconfirm --clean --distpath dist --workpath build\duz || goto :hata
  echo.
  echo Hazir: %cd%\dist\YanginKamera.exe
) else (
  set YANGIN_MODEL_PAKETI=%KIP%
  .venv\Scripts\python -m PyInstaller kurulum\YanginKamera.spec --noconfirm --clean --distpath dist\%KIP% --workpath build\%KIP% || goto :hata
  echo.
  echo Hazir: %cd%\dist\%KIP%\YanginKamera-%KIP%.exe
)

set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
  "%ISCC%" /Q /DKip=%KIP% kurulum\YanginKamera.iss || goto :hata
  echo Kurulum dosyasi: %cd%\dist\kurulum\YanginKamera-Kurulum-0.1.0.exe
) else (
  echo Inno Setup 6 kurulu degil: kurulum dosyasi uretilmedi. Kurmak icin: winget install JRSoftware.InnoSetup
)
exit /b 0

:hata
echo Derleme basarisiz.
exit /b 1
