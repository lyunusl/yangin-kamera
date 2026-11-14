; Yangın Kamera kurulum dosyası (Inno Setup 6).
;
;   kurulum\derle.cmd                       exe'yi derler, Inno Setup kuruluysa kurulum dosyasını da üretir
;   ISCC.exe kurulum\YanginKamera.iss          yalnızca kurulum dosyası: dist\kurulum\YanginKamera-Kurulum-<sürüm>.exe
;
; Adım adım kurar ve AugeLab Studio'yu da kurar; Studio penceresi hiç açılmaz:
;   1. Yangın Kamera   kullanıcı başına (yönetici izni gerekmez) %LOCALAPPDATA%\Programs\YanginKamera altına
;   2. Algılama modeli korumalı model dosyasını (yaklaşık 210 MB) Google Drive'dan indirir, SHA-256 ile doğrular ve
;                      %LOCALAPPDATA%\YanginKamera\modeller altına koyar (yalnızca community kipinde; dosya yerindeyse atlanır)
;   3. AugeLab Studio  yoksa resmî kurucuyu indirir (SHA-256 doğrulanır), Visual C++ çalışma kitaplığı eksikse Microsoft'tan
;                      indirip imzasını doğrulayarak kurar, Studio'yu sessizce kurar (olmazsa resmî kurulum penceresi)
;   4. AugeLab hesabı  hesap sayfasını tarayıcıda açar (lisans kodu hesapta görünür)
;   5. Lisans kodu     kodu Studio'nun kendi komutuyla arayüzsüz kaydeder (python -m studio verify); kod saklanmaz
; Adım 2-5 atlanabilir: program açılınca panel modeli kendisi indirir, kurulum sihirbazı Studio adımlarını gösterir.
; Kaldırınca program silinir; kullanıcı verisi (%LOCALAPPDATA%\YanginKamera: kameralar, olaylar, klipler, indirilen model)
; yerinde kalır.

#define Ad "Yangın Kamera"
#define Surum "0.1.0"
#ifndef Kip
  #define Kip "community"
#endif
#if Kip == "duz"
  #define Kaynak "..\dist\YanginKamera.exe"
#else
  #define Kaynak "..\dist\" + Kip + "\YanginKamera-" + Kip + ".exe"
#endif
; studio_kurulum.py ile aynı olmalı
#define StudioUrl "https://studio-desktop-application.s3.eu-central-1.amazonaws.com/AugeLab%20Ai%20Studio.exe"
#define StudioSha256 "cec1e2613620c57fa51c853fc2b6148bc90f978eaf76e351b4b0b0f393681bd8"
#define VcUrl "https://aka.ms/vs/17/release/vc_redist.x64.exe"
#define HesapUrl "https://account.augelab.com/"
#define StudioExe "AugeLab AI Studio.exe"
; Algılama modeli: studio_kurulum.py (MODEL_*) ile aynı olmalı. Drive kimliği tek yerde: ModelDriveKimligi.
#define ModelAdi "yangin-duman-512.onnx.isgm"
#define ModelBoyut "209948213"
#define ModelSha256 "e255740b5e76f453ab3fd48fbbb8d0d05cd5671f69a7f110568c65770745e2b0"
#define ModelDriveKimligi "16zSP5DZjS6Y15EK-BHCCZWY5cHEYfih3"
#define ModelUrl "https://drive.usercontent.google.com/download?id=" + ModelDriveKimligi + "&export=download&confirm=t"
#if Kip == "community"
  #define ModelGerekli "True"
#else
  #define ModelGerekli "False"
#endif

[Setup]
AppId={{765C268D-4954-4FD6-BBD4-85DC7A42810D}
AppName={#Ad}
AppVersion={#Surum}
AppVerName={#Ad} {#Surum}
AppPublisher={#Ad}
VersionInfoVersion={#Surum}
VersionInfoProductName={#Ad}
VersionInfoDescription={#Ad} kurulumu
DefaultDirName={autopf}\YanginKamera
DefaultGroupName={#Ad}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\kurulum
OutputBaseFilename=YanginKamera-Kurulum-{#Surum}
SetupIconFile=yangin-kamera.ico
UninstallDisplayIcon={app}\YanginKamera.exe
UninstallDisplayName={#Ad}
Compression=lzma2/fast
SolidCompression=no
WizardStyle=modern
; Açık paneli Windows'un yeniden başlatma yöneticisi kapatamıyor (konsol penceresi, takılıyor): PrepareToInstall kapatır.
CloseApplications=no
RestartApplications=no

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Kısayollar:"

[Files]
Source: "panel-kapat.ps1"; Flags: dontcopy
Source: "{#Kaynak}"; DestDir: "{app}"; DestName: "YanginKamera.exe"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\ATIFLAR.md"; DestDir: "{app}"; Flags: ignoreversion
#if Kip == "community"
Source: "community-modeller\RUST-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{autoprograms}\{#Ad}"; Filename: "{app}\YanginKamera.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#Ad}"; Filename: "{app}\YanginKamera.exe"; WorkingDir: "{app}"; Tasks: masaustu

[Run]
Filename: "{app}\YanginKamera.exe"; Description: "{#Ad} programını şimdi aç"; Flags: nowait postinstall skipifsilent

[Messages]
tr.FinishedLabel=Kurulum tamamlandı. {#Ad} açıldığında kameralarınızı ekleyebilirsiniz. AugeLab Studio arka planda çalışır; penceresi açılmaz.

[Code]
var
  ModelSayfa: TOutputMsgWizardPage;
  ModelIndirmeSayfa: TDownloadWizardPage;
  StudioSayfa: TOutputMsgWizardPage;
  HesapSayfa: TOutputMsgWizardPage;
  LisansSayfa: TInputQueryWizardPage;
  IndirmeSayfa: TDownloadWizardPage;
  StudioYeniKuruldu: Boolean;

function StudioKlasoru(): String;
begin
  Result := ExpandConstant('{localappdata}\Programs\AugeLab Studio');
end;

function StudioTamMi(Klasor: String): Boolean;
begin
  Result := FileExists(Klasor + '\{#StudioExe}') and FileExists(Klasor + '\Python\python.exe');
end;

{ Studio'nun yeri: varsayılan klasör, yoksa Windows'un "Yüklü uygulamalar" kaydındaki InstallLocation. }
function StudioYeri(): String;
var
  Koklar: array of Integer;
  Adlar: TArrayOfString;
  I, K: Integer;
  Anahtar, Ad, Yer: String;
begin
  Result := '';
  if StudioTamMi(StudioKlasoru()) then begin
    Result := StudioKlasoru();
    exit;
  end;
  SetArrayLength(Koklar, 2);
  Koklar[0] := HKCU;
  Koklar[1] := HKLM64;
  for K := 0 to 1 do begin
    Anahtar := 'Software\Microsoft\Windows\CurrentVersion\Uninstall';
    if RegGetSubkeyNames(Koklar[K], Anahtar, Adlar) then
      for I := 0 to GetArrayLength(Adlar) - 1 do
        if RegQueryStringValue(Koklar[K], Anahtar + '\' + Adlar[I], 'DisplayName', Ad) and
           (Pos('augelab', Lowercase(Ad)) > 0) and (Pos('studio', Lowercase(Ad)) > 0) and
           RegQueryStringValue(Koklar[K], Anahtar + '\' + Adlar[I], 'InstallLocation', Yer) then begin
          Yer := RemoveQuotes(Yer);
          if (Yer <> '') and StudioTamMi(Yer) then begin
            Result := Yer;
            exit;
          end;
        end;
  end;
end;

function VcKurulu(): Boolean;
var
  Deger: Cardinal;
begin
  Result := (RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Deger) and (Deger = 1)) or
            (RegQueryDWordValue(HKLM32, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Deger) and (Deger = 1));
end;

function MicrosoftImzali(Dosya: String): Boolean;
var
  Kod: Integer;
begin
  Result := Exec('powershell.exe', '-NoProfile -NonInteractive -Command "$s = Get-AuthenticodeSignature -LiteralPath ''' + Dosya +
    '''; if ($s.Status -eq ''Valid'' -and $s.SignerCertificate.Subject -match ''O=Microsoft Corporation'') { exit 0 } else { exit 1 }"',
    '', SW_HIDE, ewWaitUntilTerminated, Kod) and (Kod = 0);
end;

procedure StudioPenceresiniKapat();
var
  Kod, I: Integer;
begin
  { Resmî kurucu bitince Studio'yu kendiliğinden açarsa kapatılır: Yangın Kamera Studio'yu arayüzsüz kullanır. }
  for I := 1 to 8 do begin
    Sleep(1000);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "{#StudioExe}" /T', '', SW_HIDE, ewWaitUntilTerminated, Kod);
  end;
end;

function Indir(Url, Ad, Sha256: String): Boolean;
begin
  IndirmeSayfa.Clear;
  IndirmeSayfa.Add(Url, Ad, Sha256);
  IndirmeSayfa.Show;
  try
    try
      IndirmeSayfa.Download;
      Result := True;
    except
      Result := False;
      if not IndirmeSayfa.AbortedByUser then
        MsgBox(Ad + ' indirilemedi: ' + GetExceptionMessage, mbError, MB_OK);
    end;
  finally
    IndirmeSayfa.Hide;
  end;
end;

function ModelKlasoru(): String;
begin
  Result := ExpandConstant('{localappdata}\YanginKamera\modeller');
end;

{ Model dosyası yerinde ve boyutu doğru mu (tam SHA-256 denetimi indirmede yapılır; panel de aynı ölçütü kullanır). }
function ModelYerinde(): Boolean;
var
  Boyut: Integer;
begin
  Result := FileSize(ModelKlasoru() + '\{#ModelAdi}', Boyut) and (Boyut = {#ModelBoyut});
end;

{ Modeli indirir (Inno Setup SHA-256 özetini doğrular; Drive dosya yerine sayfa verirse özet tutmaz) ve model klasörüne
  önce .yeni adıyla, sonra asıl adıyla koyar. Olmazsa tek bir bilgi kutusu: program ilk açılışta kendisi indirir. }
procedure ModelIndir();
var
  Indirilen, Gecici, Hedef: String;
  Tamam: Boolean;
begin
  Indirilen := ExpandConstant('{tmp}\{#ModelAdi}');
  Gecici := ModelKlasoru() + '\{#ModelAdi}.yeni';
  Hedef := ModelKlasoru() + '\{#ModelAdi}';
  Tamam := False;
  ModelIndirmeSayfa.Clear;
  ModelIndirmeSayfa.Add('{#ModelUrl}', '{#ModelAdi}', '{#ModelSha256}');
  ModelIndirmeSayfa.Show;
  try
    try
      ModelIndirmeSayfa.Download;
      if ForceDirectories(ModelKlasoru()) then begin
        DeleteFile(Gecici);
        if RenameFile(Indirilen, Gecici) or CopyFile(Indirilen, Gecici, False) then begin
          DeleteFile(Hedef);
          Tamam := RenameFile(Gecici, Hedef) and ModelYerinde();
        end;
      end;
    except
      Tamam := False;
    end;
  finally
    ModelIndirmeSayfa.Hide;
    DeleteFile(Gecici);
    DeleteFile(Indirilen);
  end;
  if not Tamam then
    MsgBox('Algılama modeli indirilemedi ya da doğrulanamadı. Kuruluma devam edebilirsiniz: ' +
      '{#Ad} ilk açılışta modeli kendisi indirir (internet bağlantısı gerekir).', mbInformation, MB_OK);
end;

function StudioKur(): Boolean;
var
  Kurucu, Vc: String;
  Kod: Integer;
begin
  Result := False;
  if not VcKurulu() then begin
    if not Indir('{#VcUrl}', 'vc_redist.x64.exe', '') then exit;
    Vc := ExpandConstant('{tmp}\vc_redist.x64.exe');
    if not MicrosoftImzali(Vc) then begin
      MsgBox('Visual C++ kurulum dosyasının Microsoft imzası doğrulanamadı; çalıştırılmadı.', mbError, MB_OK);
      exit;
    end;
    StudioSayfa.MsgLabel.Caption := 'Visual C++ çalışma kitaplığı kuruluyor. Windows izin sorarsa Evet deyin.';
    if not ShellExec('', Vc, '/install /passive /norestart', '', SW_SHOW, ewWaitUntilTerminated, Kod) or
       not ((Kod = 0) or (Kod = 1638) or (Kod = 3010)) or not VcKurulu() then begin
      MsgBox('Visual C++ çalışma kitaplığı kurulamadı (kod ' + IntToStr(Kod) + ').', mbError, MB_OK);
      exit;
    end;
  end;
  if not Indir('{#StudioUrl}', 'AugeLab-Studio-Kurulum.exe', '{#StudioSha256}') then exit;
  Kurucu := ExpandConstant('{tmp}\AugeLab-Studio-Kurulum.exe');
  StudioSayfa.MsgLabel.Caption := 'AugeLab Studio kuruluyor. Birkaç dakika sürebilir; lütfen bekleyin…';
  WizardForm.NextButton.Enabled := False;
  try
    ShellExec('', Kurucu, '--silent --install-dir "' + StudioKlasoru() + '" --start-menu-shortcut', '', SW_HIDE, ewWaitUntilTerminated, Kod);
    if StudioYeri() = '' then begin
      MsgBox('Sessiz kurulum tamamlanmadı. AugeLab Studio''nun resmî kurulum penceresi açılacak; adımları orada tamamlayın.', mbInformation, MB_OK);
      ShellExec('', Kurucu, '', '', SW_SHOW, ewWaitUntilTerminated, Kod);
    end;
  finally
    WizardForm.NextButton.Enabled := True;
  end;
  Result := StudioYeri() <> '';
  if Result then begin
    StudioYeniKuruldu := True;
    StudioPenceresiniKapat();
  end else
    MsgBox('AugeLab Studio kurulamadı. Programı açınca paneldeki kurulum sihirbazıyla yeniden deneyebilirsiniz.', mbError, MB_OK);
end;

function KodGecerli(Kod: String): Boolean;
var
  I: Integer;
  C: Char;
begin
  Result := (Length(Kod) >= 6) and (Length(Kod) <= 1024);
  for I := 1 to Length(Kod) do begin
    C := Kod[I];
    if not (((C >= 'A') and (C <= 'Z')) or ((C >= 'a') and (C <= 'z')) or ((C >= '0') and (C <= '9')) or
            ((I > 1) and ((C = '.') or (C = '_') or (C = '+') or (C = '/') or (C = '=') or (C = '-')))) then
      Result := False;
  end;
end;

function OrtamYaz(Ad, Deger: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';
function OrtamSil(Ad: String; Deger: Cardinal): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function LisansKaydet(Kod: String): Boolean;
var
  Yer, Isaret: String;
  Sonuc: Integer;
  Calisti: Boolean;
begin
  Result := False;
  Yer := StudioYeri();
  WizardForm.NextButton.Enabled := False;
  LisansSayfa.SubCaptionLabel.Caption := 'Lisans kodu AugeLab Studio''ya kaydediliyor…';
  try
    { Kod yalnızca Studio'nun kendi "verify" komutuna verilir; komut satırında görünmesin diye ortam değişkeniyle
      (studio_kurulum.VERIFY ile aynı). Dosyaya ya da günlüğe yazılmaz. }
    OrtamYaz('YANGIN_LISANS_KODU', Kod);
    try
      Calisti := Exec(Yer + '\Python\python.exe', '-c "import os,runpy,sys; sys.argv=[''studio'',''verify'',' +
        'os.environ.pop(''YANGIN_LISANS_KODU'','''')]; runpy.run_module(''studio'',run_name=''__main__'',alter_sys=True)"',
        Yer, SW_HIDE, ewWaitUntilTerminated, Sonuc);
    finally
      OrtamSil('YANGIN_LISANS_KODU', 0);
    end;
    if Calisti and (Sonuc = 0) then begin
      Isaret := ExpandConstant('{localappdata}\YanginKamera');
      ForceDirectories(Isaret);
      SaveStringToFile(Isaret + '\studio-lisans.txt', GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':'), False);
      Result := True;
    end else
      MsgBox('Lisans kodu kaydedilemedi. Kodu AugeLab hesabınızdan yeniden kopyalayıp deneyin ya da internet bağlantınızı kontrol edin.', mbError, MB_OK);
  finally
    WizardForm.NextButton.Enabled := True;
    LisansSayfa.SubCaptionLabel.Caption := 'Kodu yapıştırın. Kod yalnızca AugeLab Studio''ya verilir; Yangın Kamera onu saklamaz.';
  end;
end;

procedure HesapAc(Sender: TObject);
var
  Kod: Integer;
begin
  ShellExecAsOriginalUser('open', '{#HesapUrl}?p=signup', '', '', SW_SHOWNORMAL, ewNoWait, Kod);
end;

procedure KodAl(Sender: TObject);
var
  Kod: Integer;
begin
  ShellExecAsOriginalUser('open', '{#HesapUrl}', '', '', SW_SHOWNORMAL, ewNoWait, Kod);
end;

function Dugme(Sayfa: TWizardPage; Yazi: String; Ust: Integer; Tik: TNotifyEvent): TNewButton;
begin
  Result := TNewButton.Create(Sayfa);
  Result.Parent := Sayfa.Surface;
  Result.Caption := Yazi;
  Result.Top := Ust;
  Result.Left := 0;
  Result.Width := ScaleX(220);
  Result.Height := ScaleY(28);
  Result.OnClick := Tik;
end;

procedure InitializeWizard();
begin
  IndirmeSayfa := CreateDownloadPage('AugeLab Studio', 'Gerekli dosyalar indiriliyor.', nil);
  ModelIndirmeSayfa := CreateDownloadPage('Algılama modeli', 'Algılama modeli (yaklaşık 210 MB) indiriliyor ve doğrulanıyor.', nil);
  ModelSayfa := CreateOutputMsgPage(wpInstalling, 'Algılama modeli',
    'Yangın Kamera alev ve dumanı bir yapay zekâ modeliyle algılar.',
    'Algılama modeli (yaklaşık 210 MB) kurulum dosyasına konmadı. Sonraki''ye basınca Google Drive''dan indirilir, ' +
    'SHA-256 özetiyle doğrulanır ve bu kullanıcının veri klasörüne konur. İnternet hızına göre birkaç dakika sürebilir.'#13#10#13#10 +
    'İndirme olmazsa kurulum yine tamamlanır; {#Ad} ilk açılışta modeli kendisi indirir.');
  StudioSayfa := CreateOutputMsgPage(ModelSayfa.ID, 'AugeLab Studio',
    'Yangın Kamera görüntüleri bu bilgisayardaki AugeLab Studio ile analiz eder.', '');
  HesapSayfa := CreateOutputMsgPage(StudioSayfa.ID, 'AugeLab hesabı',
    'Studio''yu etkinleştiren lisans kodu AugeLab hesabınızda görünür.',
    'AugeLab hesabınız yoksa aşağıdaki düğmeyle tarayıcıda oluşturun ve e-postanıza gelen bağlantıyla onaylayın. ' +
    'Ücretsiz Community planı yeterlidir.'#13#10#13#10'Hesabınız varsa Sonraki''ye basın.');
  Dugme(HesapSayfa, 'AugeLab hesabı oluştur ↗', ScaleY(110), @HesapAc);
  LisansSayfa := CreateInputQueryPage(HesapSayfa.ID, 'Lisans kodu',
    'AugeLab Studio arayüz açılmadan etkinleştirilir.',
    'Kodu yapıştırın. Kod yalnızca AugeLab Studio''ya verilir; Yangın Kamera onu saklamaz.');
  LisansSayfa.Add('Lisans kodu (boş bırakırsanız sonra paneldeki sihirbazdan girersiniz):', False);
  Dugme(LisansSayfa, 'Lisans kodumu al ↗', LisansSayfa.Edits[0].Top + LisansSayfa.Edits[0].Height + ScaleY(14), @KodAl);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = StudioSayfa.ID then begin
    if StudioYeri() <> '' then
      StudioSayfa.MsgLabel.Caption := 'AugeLab Studio bu bilgisayarda kurulu. Sonraki''ye basın.'#13#10#13#10 +
        'Studio arka planda çalışır; Yangın Kamera onun penceresini açmaz.'
    else
      StudioSayfa.MsgLabel.Caption := 'AugeLab Studio bu bilgisayarda kurulu değil. Sonraki''ye basınca:'#13#10#13#10 +
        '• AugeLab''in resmî kurulum dosyası indirilir ve doğrulanır,'#13#10 +
        '• Visual C++ bileşeni eksikse Microsoft''tan kurulur (Windows izin sorabilir),'#13#10 +
        '• AugeLab Studio bu kullanıcı için sessizce kurulur.'#13#10#13#10 +
        'Studio arka planda çalışır; Yangın Kamera onun penceresini açmaz.';
  end;
end;

{ Güncellemede panel açıksa kapatılır (dosyası kullanımda kalmasın). }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Kod: Integer;
begin
  Result := '';
  { Yalnızca bu klasördeki Yangın Kamera kapatılır. Betik çalışamazsa kurulum durur. }
  ExtractTemporaryFile('panel-kapat.ps1');
  if not Exec('powershell.exe', '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
              ExpandConstant('{tmp}\panel-kapat.ps1') + '" -Uygulama "' + ExpandConstant('{app}\YanginKamera.exe') + '"',
              '', SW_HIDE, ewWaitUntilTerminated, Kod) or (Kod <> 0) then
    Result := '{#Ad} kapatılamadı. Programı kapatıp kurulumu yeniden başlatın.';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  { Model yerindeyse (ya da community kipi değilse) model adımı atlanır. Studio kurulamadıysa hesap ve lisans adımları
    programdaki sihirbaza kalır. }
  if PageID = ModelSayfa.ID then
    Result := (not {#ModelGerekli}) or ModelYerinde()
  else
    Result := ((PageID = HesapSayfa.ID) or (PageID = LisansSayfa.ID)) and (StudioYeri() = '');
end;

var
  SonrakiMesgul: Boolean;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Kod: String;
begin
  { Uzun bir adım (indirme, Visual C++ ya da Studio kurulumu) sürerken düğmeye yeniden basılırsa adım ikinci kez başlamaz. }
  Result := False;
  if SonrakiMesgul then exit;
  SonrakiMesgul := True;
  try
  Result := True;
  if CurPageID = ModelSayfa.ID then begin
    { Model indirilemese de kurulum sürer (ModelIndir bilgi verir). }
    if not ModelYerinde() then
      ModelIndir();
  end else if (CurPageID = StudioSayfa.ID) and (StudioYeri() = '') then begin
    if not StudioKur() then
      Result := MsgBox('AugeLab Studio kurulmadan devam edilsin mi? Programı açınca paneldeki sihirbazla kurabilirsiniz.',
        mbConfirmation, MB_YESNO) = IDYES;
  end else if CurPageID = LisansSayfa.ID then begin
    Kod := Trim(LisansSayfa.Values[0]);
    if Kod = '' then
      Result := MsgBox('Lisans kodu girmeden devam edilsin mi? Programı açınca paneldeki sihirbazdan girebilirsiniz.',
        mbConfirmation, MB_YESNO) = IDYES
    else if not KodGecerli(Kod) then begin
      MsgBox('Lisans kodu geçersiz görünüyor. AugeLab hesabınızdaki kodu boşluksuz, olduğu gibi yapıştırın.', mbError, MB_OK);
      Result := False;
    end else begin
      Result := LisansKaydet(Kod);
      if Result then LisansSayfa.Values[0] := '';
    end;
  end;
  finally
    SonrakiMesgul := False;
  end;
end;
