#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

/* Leave console signals to the application while this process waits for it. */
static BOOL WINAPI control(DWORD event) {
    return event == CTRL_C_EVENT || event == CTRL_BREAK_EVENT;
}

int wmain(void) {
    wchar_t application[32768];
    wchar_t command[32768];
    wchar_t parent[32];
    wchar_t *arguments = GetCommandLineW();
    wchar_t *extension;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    DWORD status = 1;
    DWORD length = GetModuleFileNameW(NULL, application, 32768);
    if (!length || length >= 32768) {
        fputs("Could not locate application launcher.\n", stderr);
        return 1;
    }
    extension = wcsrchr(application, L'.');
    if (!extension || wcscpy_s(extension, 32768 - (extension - application), L".exe")) {
        fputs("Invalid application launcher path.\n", stderr);
        return 1;
    }

    /* The first command-line token is the launcher path, not a user argument. */
    if (*arguments == L'"') {
        ++arguments;
        while (*arguments && *arguments != L'"') ++arguments;
        if (*arguments) ++arguments;
    } else {
        while (*arguments && *arguments != L' ' && *arguments != L'\t') ++arguments;
    }
    while (*arguments == L' ' || *arguments == L'\t') ++arguments;
    if (swprintf_s(command, 32768, L"\"%ls\" %ls", application,
                   *arguments ? arguments : L"tui") < 0) {
        fputs("Application command line is too long.\n", stderr);
        return 1;
    }
    swprintf_s(parent, 32, L"%lu", GetCurrentProcessId());
    /* Each terminal launch owns its runtime independently of the GUI lifetime. */
    if (!SetEnvironmentVariableW(L"MDHELPER_CONSOLE_PID", parent) ||
        !SetEnvironmentVariableW(L"PYINSTALLER_RESET_ENVIRONMENT", L"1")) {
        fputs("Could not configure the application environment.\n", stderr);
        return 1;
    }
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    SetConsoleCtrlHandler(control, TRUE);
    if (!CreateProcessW(application, command, NULL, NULL, TRUE, 0, NULL, NULL,
                        &startup, &process)) {
        fwprintf(stderr, L"Could not start %ls (Windows error %lu).\n",
                 application, GetLastError());
        return 1;
    }
    CloseHandle(process.hThread);
    if (WaitForSingleObject(process.hProcess, INFINITE) == WAIT_OBJECT_0) {
        GetExitCodeProcess(process.hProcess, &status);
    }
    CloseHandle(process.hProcess);
    return (int)status;
}
