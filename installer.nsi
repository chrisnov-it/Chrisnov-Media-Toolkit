; Chrisnov Media Toolkit - NSIS Installer Script
; Requires: NSIS 3.x (https://nsis.sourceforge.io/)
; Usage: makensis installer.nsi

!define PRODUCT_NAME "Chrisnov Media Toolkit"
!define PRODUCT_VERSION "0.1.0-beta.5"
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
!insertmacro MUI_PAGE_LICENSE "LICENSE"
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
  
  ; Placeholder — actual .exe will be copied by build script
  ; File "dist\chrisnov-media-toolkit-lite.exe"
  ; For now, assume build-windows.yml renames to chrisnov-media-toolkit.exe
  File "dist\chrisnov-media-toolkit.exe"
  
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

Section /o "FFmpeg Bundled (for Lite builds)" SecBundled
  SetOutPath "$INSTDIR\bin"
  ; Placeholder — actual ffmpeg.exe + ffprobe.exe copied by build script if Bundled selected
  ; File "bin\ffmpeg.exe"
  ; File "bin\ffprobe.exe"
SectionEnd

; Section descriptions
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} "Main application executable. Required."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecBundled} "Include FFmpeg binaries (recommended if you don't have FFmpeg installed system-wide). Lite users can skip this."
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
