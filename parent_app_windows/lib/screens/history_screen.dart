import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

/// Displays the browsing history for a given child profile.
///
/// Features:
/// - Protocol badge (HTTP / HTTPS)
/// - Content category chip (adult, violence, gambling, social, games, unknown)
/// - Blocked / allowed indicator
/// - Formatted timestamp
/// - Filter bar (All / Blocked / protocol / category)
class HistoryScreen extends StatefulWidget {
  final String childId;
  final String childName;
  final String backendBaseUrl;

  const HistoryScreen({
    Key? key,
    required this.childId,
    required this.childName,
    required this.backendBaseUrl,
  }) : super(key: key);

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> _allEntries = [];
  bool _loading = true;
  String? _error;

  // Active filters
  String _filterProtocol = 'All'; // All | HTTP | HTTPS
  String _filterCategory = 'All'; // All | adult | violence | gambling | social | games | unknown
  bool? _filterBlocked;            // null = All, true = blocked, false = allowed

  static const _protocols = ['All', 'HTTP', 'HTTPS'];
  static const _categories = [
    'All',
    'adult',
    'violence',
    'gambling',
    'social',
    'games',
    'unknown',
  ];

  @override
  void initState() {
    super.initState();
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final uri = Uri.parse(
        '${widget.backendBaseUrl}/api/v1/history/${widget.childId}',
      );
      final response = await http.get(uri);
      if (response.statusCode == 200) {
        final data = json.decode(response.body) as List<dynamic>;
        setState(() {
          _allEntries =
              data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
          _loading = false;
        });
      } else {
        setState(() {
          _error = 'Server error: ${response.statusCode}';
          _loading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Connection error: $e';
        _loading = false;
      });
    }
  }

  List<Map<String, dynamic>> get _filtered {
    return _allEntries.where((entry) {
      if (_filterProtocol != 'All' &&
          (entry['protocol'] ?? '').toString().toUpperCase() !=
              _filterProtocol) {
        return false;
      }
      if (_filterCategory != 'All' &&
          (entry['category'] ?? 'unknown').toString() != _filterCategory) {
        return false;
      }
      if (_filterBlocked != null &&
          (entry['blocked'] as bool? ?? false) != _filterBlocked) {
        return false;
      }
      return true;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('History – ${widget.childName}'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: _fetchHistory,
          ),
        ],
      ),
      body: Column(
        children: [
          _buildFilterBar(),
          Expanded(child: _buildBody()),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Card(
      margin: const EdgeInsets.all(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Wrap(
          spacing: 12,
          runSpacing: 8,
          alignment: WrapAlignment.start,
          children: [
            // Protocol filter
            DropdownButton<String>(
              value: _filterProtocol,
              hint: const Text('Protocol'),
              items: _protocols
                  .map(
                    (p) => DropdownMenuItem(value: p, child: Text(p)),
                  )
                  .toList(),
              onChanged: (v) => setState(() => _filterProtocol = v ?? 'All'),
            ),
            // Category filter
            DropdownButton<String>(
              value: _filterCategory,
              hint: const Text('Category'),
              items: _categories
                  .map(
                    (c) => DropdownMenuItem(
                      value: c,
                      child: Text(
                        c == 'All' ? 'All categories' : c,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (v) => setState(() => _filterCategory = v ?? 'All'),
            ),
            // Blocked filter
            DropdownButton<bool?>(
              value: _filterBlocked,
              hint: const Text('Status'),
              items: const [
                DropdownMenuItem(value: null, child: Text('All')),
                DropdownMenuItem(value: true, child: Text('Blocked')),
                DropdownMenuItem(value: false, child: Text('Allowed')),
              ],
              onChanged: (v) => setState(() => _filterBlocked = v),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 12),
            ElevatedButton.icon(
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
              onPressed: _fetchHistory,
            ),
          ],
        ),
      );
    }
    final entries = _filtered;
    if (entries.isEmpty) {
      return const Center(child: Text('No history entries match the filter.'));
    }
    return ListView.separated(
      itemCount: entries.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) => _buildEntryTile(entries[index]),
    );
  }

  Widget _buildEntryTile(Map<String, dynamic> entry) {
    final protocol = (entry['protocol'] ?? 'HTTP').toString().toUpperCase();
    final category = (entry['category'] ?? 'unknown').toString();
    final blocked = entry['blocked'] as bool? ?? false;
    final url = entry['url']?.toString() ?? '';
    final timestamp = _formatTimestamp(entry['timestamp']?.toString());

    return ListTile(
      leading: _ProtocolBadge(protocol: protocol),
      title: Text(
        url,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: blocked ? Colors.red.shade700 : null,
          decoration: blocked ? TextDecoration.lineThrough : null,
        ),
      ),
      subtitle: Row(
        children: [
          _CategoryChip(category: category),
          const SizedBox(width: 8),
          Text(
            timestamp,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
      trailing: blocked
          ? const Icon(Icons.block, color: Colors.red, size: 20)
          : const Icon(Icons.check_circle, color: Colors.green, size: 20),
    );
  }

  String _formatTimestamp(String? raw) {
    if (raw == null) return '';
    try {
      final dt = DateTime.parse(raw).toLocal();
      return '${dt.year}-${_pad(dt.month)}-${_pad(dt.day)} '
          '${_pad(dt.hour)}:${_pad(dt.minute)}:${_pad(dt.second)}';
    } catch (_) {
      return raw;
    }
  }

  String _pad(int v) => v.toString().padLeft(2, '0');
}

// ---------------------------------------------------------------------------
// Small reusable widgets
// ---------------------------------------------------------------------------

class _ProtocolBadge extends StatelessWidget {
  final String protocol;
  const _ProtocolBadge({required this.protocol});

  @override
  Widget build(BuildContext context) {
    final isHttps = protocol == 'HTTPS';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: isHttps ? Colors.green.shade100 : Colors.orange.shade100,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
          color: isHttps ? Colors.green.shade400 : Colors.orange.shade400,
        ),
      ),
      child: Text(
        protocol,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.bold,
          color: isHttps ? Colors.green.shade800 : Colors.orange.shade800,
        ),
      ),
    );
  }
}

class _CategoryChip extends StatelessWidget {
  final String category;
  const _CategoryChip({required this.category});

  static const _chipBackgroundOpacity = 0.12;

  static const _colors = <String, MaterialColor>{
    'adult': Colors.red,
    'violence': Colors.deepOrange,
    'gambling': Colors.purple,
    'social': Colors.blue,
    'games': Colors.teal,
    'unknown': Colors.grey,
  };

  @override
  Widget build(BuildContext context) {
    final color = _colors[category] ?? Colors.grey;
    return Chip(
      label: Text(category),
      labelStyle: TextStyle(fontSize: 11, color: color.shade800),
      backgroundColor: color.withOpacity(_chipBackgroundOpacity),
      side: BorderSide(color: color.shade300),
      padding: EdgeInsets.zero,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      visualDensity: VisualDensity.compact,
    );
  }
}
