; ModularCV Desktop installer hooks (Tauri "installerHooks").
;
; The embedded engine needs the Microsoft Visual C++ Redistributable (x64). ModularCV does not ship it: Microsoft distributes it
; itself, and installing it may need administrator rights, which this per-user installer never asks for. This hook only LOOKS for the
; Redistributable (the registry key every Redistributable writes) and warns when it is missing or too old. It downloads and installs
; nothing. In a silent installation nothing is shown and the installation goes on; the application itself explains the problem.
;
; The minimum version is the one recorded in desktop/licenses/vc-runtime-prerequisite.json and in src/vcruntime.rs; a test keeps them equal.
!define MCV_VC_MIN_MAJOR 14
!define MCV_VC_MIN_MINOR 44
!define MCV_VC_MIN_BUILD 35229
!define MCV_VC_MIN_TEXT "14.44.35229"
!define MCV_VC_KEY "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"
!define MCV_VC_URL "https://aka.ms/vc14/vc_redist.x64.exe"

!macro NSIS_HOOK_PREINSTALL
  Push $0
  Push $1
  Push $2
  Push $3
  SetRegView 64
  ReadRegDWORD $0 HKLM "${MCV_VC_KEY}" "Installed"
  ReadRegDWORD $1 HKLM "${MCV_VC_KEY}" "Major"
  ReadRegDWORD $2 HKLM "${MCV_VC_KEY}" "Minor"
  ReadRegDWORD $3 HKLM "${MCV_VC_KEY}" "Bld"
  SetRegView 32
  IntCmp $0 1 mcv_vc_check mcv_vc_missing mcv_vc_missing
  mcv_vc_check:
  IntCmp $1 ${MCV_VC_MIN_MAJOR} 0 mcv_vc_too_old mcv_vc_ok
  IntCmp $2 ${MCV_VC_MIN_MINOR} 0 mcv_vc_too_old mcv_vc_ok
  IntCmp $3 ${MCV_VC_MIN_BUILD} mcv_vc_ok mcv_vc_too_old mcv_vc_ok
  mcv_vc_missing:
  DetailPrint "Microsoft Visual C++ Redistributable (x64) ${MCV_VC_MIN_TEXT} or newer: not found."
  IfSilent mcv_vc_ok
  MessageBox MB_YESNO|MB_ICONEXCLAMATION "Microsoft Visual C++ Redistributable (x64) ${MCV_VC_MIN_TEXT} or newer was not found on this computer.$\r$\n$\r$\nModularCV does not include it: Microsoft provides it separately. Install it from ${MCV_VC_URL} (administrator rights may be required), then run this installer again.$\r$\n$\r$\nContinue installing ModularCV anyway? The application will explain the problem and will not start its engine until the runtime is installed.$\r$\n$\r$\n---$\r$\n$\r$\nLe Redistributable Microsoft Visual C++ (x64) ${MCV_VC_MIN_TEXT} ou plus recent est introuvable sur cet ordinateur. ModularCV ne l'inclut pas : Microsoft le fournit separement (${MCV_VC_URL}). Continuer quand meme ?" IDYES mcv_vc_ok
  Abort
  mcv_vc_too_old:
  DetailPrint "Microsoft Visual C++ Redistributable (x64): installed version is older than ${MCV_VC_MIN_TEXT}."
  IfSilent mcv_vc_ok
  MessageBox MB_YESNO|MB_ICONEXCLAMATION "The Microsoft Visual C++ Redistributable (x64) installed on this computer is older than ${MCV_VC_MIN_TEXT}.$\r$\n$\r$\nModularCV does not include it: Microsoft provides it separately. Update it from ${MCV_VC_URL} (administrator rights may be required), then run this installer again.$\r$\n$\r$\nContinue installing ModularCV anyway? The application will explain the problem and will not start its engine until the runtime is updated.$\r$\n$\r$\n---$\r$\n$\r$\nLe Redistributable Microsoft Visual C++ (x64) installe est plus ancien que ${MCV_VC_MIN_TEXT}. ModularCV ne l'inclut pas : mettez-le a jour depuis ${MCV_VC_URL}. Continuer quand meme ?" IDYES mcv_vc_ok
  Abort
  mcv_vc_ok:
  Pop $3
  Pop $2
  Pop $1
  Pop $0
!macroend
