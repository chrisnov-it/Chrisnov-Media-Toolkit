; Chrisnov Media Toolkit - NSIS Installer Script
; Requires: NSIS 3.x (https://nsis.sourceforge.io/)
;
; Usage (from the project root, after build-windows.ps1 has produced dist\):
;   makensis installer.nsi
;
; Optional defines:
;   makensis -DPRODUCT_VERSION=0.2.0-beta.4 installer.nsi
;       Override the version shown in Add/Remove Programs and the installer
;       filename. Default below should be kept in sync with APP_VERSION in
;       app/constants.py.
;   makensis -DPRODUCT_LICENSE=LICENSE installer.nsi
;       Include a license page (file must exist at the repo root).
;
; Build inputs:
;   dist\chrisnov-media-toolkit-lite.exe   (from: .\build-windows.ps1 -Type Lite)
;   bin\ffmpeg.exe, bin\ffprobe.exe        (only needed for the optional
;                                           "Include FFmpeg" component)

!define PRODUCT_NAME "Chrisnov Media Toolkit"
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "0.2.0-beta.4"
endif
!define PRODUCT_PUBLISHER "Chrisnov IT Solutions"
!define PRODUCT_WEB_SITE "https://chrisnov.com"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "ChrisnovMediaToolkit-Setup-v${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\Chrisnov Media Toolkit"
InstallDirRegKey HKLM "${PRODUCT_UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

; Modern UI
!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!ifdef PRODUCT_LICENSE
  !insertmacro MUI_PAGE_LICENSE "${PRODUCT_LICENSE}"
!endif
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\chrisnov-media-toolkit.exe"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Create Desktop Shortcut"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language
!insertmacro MUI_LANGUAGE "English"

; Sections
Section "Core Files (required)" SecCore
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; Main executable — produced by build-windows.ps1 as the Lite build.
  ; Installed under the stable name the shortcuts and uninstaller reference.
  File /oname=chrisnov-media-toolkit.exe "dist\chrisnov-media-toolkit-lite.exe"

  ; Create Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\chrisnov-media-toolkit.exe"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\uninst.exe"

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninst.exe"

  ; Write registry keys for Add/Remove Programs
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\chrisnov-media-toolkit.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "InstallLocation" "$INSTDIR"
SectionEnd

Section /o "Include FFmpeg (~150 MB)" SecBundled
  SetOutPath "$INSTDIR\bin"
  File "bin\ffmpeg.exe"
  File "bin\ffprobe.exe"
  ; GPL redistribution requirement: ship FFmpeg's licence text alongside the
  ; binaries when build-windows.ps1 saved it (see docs/THIRD-PARTY.md).
  !if /FileExists "bin\FFMPEG-LICENSE.txt"
    File "bin\FFMPEG-LICENSE.txt"
  !endif
SectionEnd

; Section descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "Chrisnov Media Toolkit application. Required. Without FFmpeg (below or on your system PATH), downloads still work but merging/conversion features are unavailable."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecBundled} "Include FFmpeg binaries (~150 MB additional), installed into the app's bin folder so the app finds them automatically. Required for audio/video conversion and yt-dlp format merging. Skip this if FFmpeg is already installed on your system (recommended for advanced users)."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; Desktop shortcut function
Function CreateDesktopShortcut
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\chrisnov-media-toolkit.exe"
FunctionEnd

; Uninstaller
Section Uninstall
  Delete "$INSTDIR\chrisnov-media-toolkit.exe"
  Delete "$INSTDIR\bin\ffmpeg.exe"
  Delete "$INSTDIR\bin\ffprobe.exe"
  Delete "$INSTDIR\bin\FFMPEG-LICENSE.txt"
  Delete "$INSTDIR\uninst.exe"
  RMDir "$INSTDIR\bin"
  RMDir "$INSTDIR"

  Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk"
  RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"

  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"

  SetAutoClose true
SectionEnd
