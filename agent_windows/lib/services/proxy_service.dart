import 'dart:ffi';
import 'dart:io';

/// Windows proxy configuration via the Internet Settings registry key.
///
/// Manages WinINet proxy settings so that the parent-app (and any process
/// using the system proxy) can still reach the backend API on port 8000
/// even when the child-filtering proxy is active.
class ProxyService {
  static const String _regPath =
      r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings';

  /// Addresses that bypass the filtering proxy.
  ///
  /// Only the backend server host and loopback addresses are excluded so that
  /// child browsing on the local network is still filtered.  `<local>` covers
  /// unqualified host names (e.g. intranet sites without a dot).
  static const String _proxyOverride = 'localhost;127.0.0.1;<local>';

  // WinINet option constants used to refresh settings at runtime.
  static const int _internetOptionSettingsChanged = 39;
  static const int _internetOptionRefresh = 37;

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /// Activate the filtering proxy at [proxyAddress] (e.g. `"192.168.1.1:3128"`).
  ///
  /// The backend server and local addresses are excluded via [_proxyOverride]
  /// so that the parent-app can still communicate with the backend.
  static Future<void> setProxy(String proxyAddress) async {
    await _setDword('ProxyEnable', 1);
    await _setString('ProxyServer', proxyAddress);
    await _setString('ProxyOverride', _proxyOverride);
    _refreshWinINet();
  }

  /// Route ALL traffic through the filtering proxy (block-all mode).
  ///
  /// Even in this mode the backend server remains reachable via the override.
  static Future<void> blockAllTraffic(String proxyAddress) async {
    await _setDword('ProxyEnable', 1);
    await _setString('ProxyServer', proxyAddress);
    await _setString('ProxyOverride', _proxyOverride);
    _refreshWinINet();
  }

  /// Disable the proxy and remove all override rules.
  static Future<void> disableProxy() async {
    await _setDword('ProxyEnable', 0);
    await _deleteValueIfExists('ProxyServer');
    await _deleteValueIfExists('ProxyOverride');
    _refreshWinINet();
  }

  // ---------------------------------------------------------------------------
  // Registry helpers (thin wrappers around `reg.exe`)
  // ---------------------------------------------------------------------------

  static Future<void> _setDword(String name, int value) async {
    await _runReg([
      'add', _regPath,
      '/v', name,
      '/t', 'REG_DWORD',
      '/d', value.toString(),
      '/f',
    ]);
  }

  static Future<void> _setString(String name, String value) async {
    await _runReg([
      'add', _regPath,
      '/v', name,
      '/t', 'REG_SZ',
      '/d', value,
      '/f',
    ]);
  }

  /// Deletes a registry value if it exists; silently succeeds if not found.
  static Future<void> _deleteValueIfExists(String name) async {
    final result = await Process.run(
      'reg',
      ['delete', _regPath, '/v', name, '/f'],
      runInShell: true,
    );
    // Exit code 1 with "unable to find" message means value didn't exist – not an error.
    if (result.exitCode != 0 &&
        !result.stderr.toString().toLowerCase().contains('unable to find')) {
      throw ProcessException(
        'reg',
        ['delete', _regPath, '/v', name, '/f'],
        result.stderr.toString(),
        result.exitCode,
      );
    }
  }

  /// Notify WinINet to reload proxy settings without requiring a process restart.
  ///
  /// Calls `InternetSetOption` with `INTERNET_OPTION_SETTINGS_CHANGED` (39)
  /// followed by `INTERNET_OPTION_REFRESH` (37) via the `wininet.dll` API.
  static void _refreshWinINet() {
    try {
      final wininet = DynamicLibrary.open('wininet.dll');
      final internetSetOption = wininet.lookupFunction<
          Int32 Function(Pointer, Uint32, Pointer, Uint32),
          int Function(Pointer, int, Pointer, int)>('InternetSetOptionW');
      internetSetOption(nullptr, _internetOptionSettingsChanged, nullptr, 0);
      internetSetOption(nullptr, _internetOptionRefresh, nullptr, 0);
    } catch (_) {
      // Non-fatal: the registry values are already written; changes will take
      // effect the next time WinINet initialises (e.g. on next browser start).
    }
  }

  static Future<void> _runReg(List<String> args) async {
    final result = await Process.run('reg', args, runInShell: true);
    if (result.exitCode != 0) {
      throw ProcessException(
        'reg',
        args,
        result.stderr.toString(),
        result.exitCode,
      );
    }
  }
}
