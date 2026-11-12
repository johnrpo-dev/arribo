import 'package:flutter/material.dart';

void main() {
  runApp(const ArriboConductorApp());
}

class ArriboConductorApp extends StatelessWidget {
  const ArriboConductorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'Arribo conductor',
      home: Scaffold(
        body: Center(child: Text('Arribo conductor')),
      ),
    );
  }
}
