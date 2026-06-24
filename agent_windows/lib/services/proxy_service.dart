import 'dart:io';

/// Service managing Windows Internet proxy settings via the registry.
///
/// The proxy is configured through the Windows registry key:
/// HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings
///
/// A [ProxyOverride] entry is always added so that the backend server
/// (port 8000) and all local addresses are never redirected through the
/// proxy.  This allows the parent application running on the same machine
/// to reach the backend even while the proxy is active.
class ProxyService {
  static const String _registryPath =
      r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings';

  /// Addresses that must bypass the proxy:
  ///   - 127.0.0.1        localhost loopback
  ///   - localhost         hostname alias
  ///   - <local>          Windows built-in wildcard for all intranet hosts
  ///   - The backend server host/port (port 8000)
  static const String _proxyOverride =
      '127.0.0.1;localhost;192.168.220.131:8000;<local>';

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /// Activate the proxy on [host]:[port] and exclude backend / local traffic.
  Future<void> setProxy(String host, int port) async {
    await _applyProxy(host, port);
  }

  /// Block all traffic by routing through [host]:[port] while keeping the
  /// backend server and localhost reachable.
  Future<void> blockAllTraffic(String host, int port) async {
    await _applyProxy(host, port);
  }

  /// Shared implementation used by both [setProxy] and [blockAllTraffic].
  Future<void> _applyProxy(String host, int port) async {
    await _runReg('add', _registryPath, 'ProxyEnable', 'REG_DWORD', '1');
    await _runReg(
        'add', _registryPath, 'ProxyServer', 'REG_SZ', '$host:$port');
    await _runReg(
        'add', _registryPath, 'ProxyOverride', 'REG_SZ', _proxyOverride);
  }

  /// Disable the proxy and remove override settings.
  Future<void> disableProxy() async {
    await _runReg('add', _registryPath, 'ProxyEnable', 'REG_DWORD', '0');
    await _runReg('delete', _registryPath, 'ProxyServer');
    await _runReg('delete', _registryPath, 'ProxyOverride');
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /// Run a `reg` command.
  ///
  /// For `add`  commands: [valueName] and subsequent arguments are required.
  /// For `delete` commands: [valueName] is optional (deletes only that value).
  Future<void> _runReg(
    String action,
    String keyPath,
    String valueName, [
    String? type,
    String? data,
  ]) async {
    final args = <String>[action, keyPath];

    if (action == 'add') {
      args.addAll(['/v', valueName, '/t', type!, '/d', data!, '/f']);
    } else if (action == 'delete') {
      // Delete a specific named value; /f suppresses the confirmation prompt.
      args.addAll(['/v', valueName, '/f']);
    }

    final result = await Process.run('reg', args, runInShell: true);
    if (result.exitCode != 0) {
      // Non-fatal: log and continue so a single failure doesn't crash the agent.
      stderr.writeln(
          '[ProxyService] reg $action failed (${result.exitCode}): ${result.stderr}');
    }
  }
}
