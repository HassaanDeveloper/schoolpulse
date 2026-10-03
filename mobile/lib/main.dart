import 'package:flutter/material.dart';

import 'app.dart';
import 'core/network/supabase_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SupabaseService.instance.initialize();
  runApp(const SchoolPulseApp());
}