; popup.asm
section .text
    global main
    extern MessageBoxA
    extern ExitProcess

main:
    ; Align stack to 16 bytes (required by Windows x64 ABI)
    push rbp
    mov rbp, rsp
    sub rsp, 32             ; Allocate shadow space (must be 16-byte aligned)
    
    ; Sample comparison instructions
    cmp rax, 0
    cmp rdx, 0
    
    ; MessageBoxA(HWND hWnd, LPCSTR lpText, LPCSTR lpCaption, UINT uType)
    ; Windows x64 calling convention: RCX, RDX, R8, R9
    
    xor rcx, rcx            ; hWnd = NULL
    lea rdx, [rel msg_text] ; lpText
    lea r8, [rel msg_title] ; lpCaption
    xor r9d, r9d            ; uType = MB_OK (0)
    
    call MessageBoxA
    
    ; Exit cleanly
    xor ecx, ecx            ; Return code 0
    call ExitProcess
    
    ; Cleanup (unreachable but included for completeness)
    add rsp, 32
    pop rbp
    ret

section .data
    msg_text db 'Hello, World!', 0
    msg_title db 'Popup', 0