import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

/// A screen that displays the browsing history of a child profile.
///
/// Features:
///  - Shows both HTTP and HTTPS entries with a protocol badge.
///  - Displays the content category (adult, violence, gambling, social, games).
///  - Colour-codes blocked vs. allowed visits.
///  - Allows filtering by protocol, blocked status, and category.
///  - Formats timestamps in a human-readable way.
class HistoryScreen extends StatefulWidget {
  final String childId;
  final String childName;
  final String backendBaseUrl;
  final String authToken;

  const HistoryScreen({
    Key? key,
    required this.childId,
    required this.childName,
    required this.backendBaseUrl,
    required this.authToken,
  }) : super(key: key);

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<Map<String, dynamic>> _allEntries = [];
  bool _loading = true;
  String? _error;

  // Filter state
  String _filterProtocol = 'ALL'; // ALL | HTTP | HTTPS
  String _filterStatus = 'ALL';   // ALL | BLOCKED | ALLOWED
  String _filterCategory = 'ALL'; // ALL | adult | violence | gambling | social | games | unknown

  static const List<String> _protocols = ['ALL', 'HTTP', 'HTTPS'];
  static const List<String> _statuses = ['ALL', 'BLOCKED', 'ALLOWED'];
  static const List<String> _categories = [
    'ALL',
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

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  Future<void> _fetchHistory() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final uri =
          Uri.parse('${widget.backendBaseUrl}/api/v1/history/${widget.childId}');
      final response = await http.get(
        uri,
        headers: {'Authorization': 'Bearer ${widget.authToken}'},
      );
      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        setState(() {
          _allEntries = data.cast<Map<String, dynamic>>();
          _loading = false;
        });
      } else {
        setState(() {
          _error = 'Server error ${response.statusCode}';
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

  // ---------------------------------------------------------------------------
  // Filtering
  // ---------------------------------------------------------------------------

  List<Map<String, dynamic>> get _filteredEntries {
    return _allEntries.where((entry) {
      final protocol = (entry['protocol'] as String? ?? 'HTTP').toUpperCase();
      final blocked = entry['blocked'] == true;
      final category = (entry['category'] as String? ?? 'unknown').toLowerCase();

      if (_filterProtocol != 'ALL' && protocol != _filterProtocol) return false;
      if (_filterStatus == 'BLOCKED' && !blocked) return false;
      if (_filterStatus == 'ALLOWED' && blocked) return false;
      if (_filterCategory != 'ALL' && category != _filterCategory) return false;
      return true;
    }).toList();
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  String _formatTimestamp(dynamic raw) {
    if (raw == null) return '';
    try {
      final dt = DateTime.parse(raw.toString()).toLocal();
      return '${dt.year}-${_pad(dt.month)}-${_pad(dt.day)} '
          '${_pad(dt.hour)}:${_pad(dt.minute)}:${_pad(dt.second)}';
    } catch (_) {
      return raw.toString();
    }
  }

  String _pad(int v) => v.toString().padLeft(2, '0');

  Color _protocolColor(String protocol) {
    return protocol.toUpperCase() == 'HTTPS' ? Colors.green : Colors.blue;
  }

  Color _categoryColor(String category) {
    switch (category.toLowerCase()) {
      case 'adult':
        return Colors.red;
      case 'violence':
        return Colors.deepOrange;
      case 'gambling':
        return Colors.purple;
      case 'social':
        return Colors.cyan;
      case 'games':
        return Colors.indigo;
      default:
        return Colors.grey;
    }
  }

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Historique — ${widget.childName}'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Actualiser',
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

  // ---------------------------------------------------------------------------
  // Filter bar
  // ---------------------------------------------------------------------------

  Widget _buildFilterBar() {
    return Container(
      color: Colors.grey[100],
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Wrap(
        spacing: 12,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          _buildDropdown('Protocole', _protocols, _filterProtocol,
              (v) => setState(() => _filterProtocol = v!)),
          _buildDropdown('Statut', _statuses, _filterStatus,
              (v) => setState(() => _filterStatus = v!)),
          _buildDropdown('Catégorie', _categories, _filterCategory,
              (v) => setState(() => _filterCategory = v!)),
        ],
      ),
    );
  }

  Widget _buildDropdown(
    String label,
    List<String> items,
    String value,
    ValueChanged<String?> onChanged,
  ) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text('$label: ',
            style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 13)),
        DropdownButton<String>(
          value: value,
          items: items
              .map((i) => DropdownMenuItem(value: i, child: Text(i)))
              .toList(),
          onChanged: onChanged,
          isDense: true,
        ),
      ],
    );
  }

  // ---------------------------------------------------------------------------
  // Body
  // ---------------------------------------------------------------------------

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
            const SizedBox(height: 8),
            ElevatedButton(
                onPressed: _fetchHistory, child: const Text('Réessayer')),
          ],
        ),
      );
    }

    final entries = _filteredEntries;
    if (entries.isEmpty) {
      return const Center(child: Text('Aucune entrée pour ces filtres.'));
    }

    return ListView.separated(
      itemCount: entries.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) => _buildEntryTile(entries[index]),
    );
  }

  Widget _buildEntryTile(Map<String, dynamic> entry) {
    final url = entry['url'] as String? ?? '';
    final protocol = (entry['protocol'] as String? ?? 'HTTP').toUpperCase();
    final category = (entry['category'] as String? ?? 'unknown').toLowerCase();
    final blocked = entry['blocked'] == true;
    final timestamp = _formatTimestamp(entry['timestamp']);

    return ListTile(
      leading: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Protocol badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
            decoration: BoxDecoration(
              color: _protocolColor(protocol),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              protocol,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 10,
                  fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(height: 4),
          // Blocked icon
          Icon(
            blocked ? Icons.block : Icons.check_circle_outline,
            color: blocked ? Colors.red : Colors.green,
            size: 18,
          ),
        ],
      ),
      title: Text(
        url,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: blocked ? Colors.red[700] : Colors.black87,
          fontSize: 14,
        ),
      ),
      subtitle: Row(
        children: [
          // Category chip
          Container(
            margin: const EdgeInsets.only(top: 4, right: 6),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: _categoryColor(category).withOpacity(0.15),
              border: Border.all(color: _categoryColor(category)),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              category,
              style: TextStyle(
                  fontSize: 11,
                  color: _categoryColor(category),
                  fontWeight: FontWeight.w500),
            ),
          ),
          // Timestamp
          Expanded(
            child: Text(
              timestamp,
              style:
                  const TextStyle(fontSize: 11, color: Colors.black54),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
      isThreeLine: true,
    );
  }
}
