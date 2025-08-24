#!/usr/bin/env python3
"""
Script de test pour vérifier l'intégration du Base Home
"""

import requests
import json
import time
import socketio
from datetime import datetime

BASE_URL = "http://localhost:3333"


def test_api_endpoints():
    """Test des endpoints API du dashboard"""
    print("=== Test des endpoints API du Base ===\n")
    
    endpoints = [
        ("/api/dashboard/summary", "GET", None),
        ("/api/dashboard/modules/status", "GET", None),
        ("/api/dashboard/analytics/realtime", "GET", None),
        ("/api/dashboard/alerts", "GET", None),
        ("/api/dashboard/storage", "GET", None),
        ("/api/dashboard/config", "GET", None),
        ("/api/dashboard/insights", "GET", None),
        ("/api/dashboard/performance", "GET", None),
        ("/api/dashboard/activity-log", "GET", None)
    ]
    
    success_count = 0
    
    for endpoint, method, data in endpoints:
        try:
            url = f"{BASE_URL}{endpoint}"
            if method == "GET":
                response = requests.get(url)
            else:
                response = requests.post(url, json=data)
            
            if response.status_code == 200:
                print(f"✅ {method} {endpoint} - OK")
                success_count += 1
                
                # Afficher un aperçu des données
                data = response.json()
                if isinstance(data, dict):
                    keys = list(data.keys())[:3]
                    print(f"   Données: {keys}...")
            else:
                print(f"❌ {method} {endpoint} - Erreur {response.status_code}")
                print(f"   Message: {response.text[:100]}")
        
        except Exception as e:
            print(f"❌ {method} {endpoint} - Exception: {e}")
    
    print(f"\n✨ Tests API réussis: {success_count}/{len(endpoints)}")
    return success_count == len(endpoints)


def test_websocket_connection():
    """Test de la connexion WebSocket au dashboard"""
    print("\n=== Test de la connexion WebSocket ===\n")
    
    sio = socketio.Client()
    test_results = {
        'connected': False,
        'joined_module': False,
        'received_data': False,
        'data_sample': None
    }
    
    @sio.on('connect')
    def on_connect():
        print("✅ WebSocket connecté")
        test_results['connected'] = True
        
        # Rejoindre le module dashboard
        sio.emit('join_module', {'module': 'dashboard'})
    
    @sio.on('module_joined')
    def on_module_joined(data):
        print(f"✅ Module rejoint: {data.get('module')}")
        test_results['joined_module'] = True
        
        # Demander le résumé du dashboard
        sio.emit('request_summary', {})
    
    @sio.on('dashboard_summary')
    def on_dashboard_summary(data):
        print("✅ Données dashboard reçues")
        test_results['received_data'] = True
        test_results['data_sample'] = data
        
        # Afficher un aperçu
        if 'global_stats' in data:
            stats = data['global_stats']
            print(f"   - Modules actifs: {stats.get('active_modules', 0)}")
            print(f"   - Points de données: {stats.get('data_points', 0)}")
            print(f"   - Qualité session: {stats.get('session_quality', 0)}%")
        
        sio.disconnect()
    
    @sio.on('error')
    def on_error(data):
        print(f"❌ Erreur WebSocket: {data}")
    
    try:
        # Connexion
        sio.connect(BASE_URL)
        
        # Attendre les réponses
        time.sleep(3)
        
        # Vérifier les résultats
        if test_results['connected'] and test_results['joined_module'] and test_results['received_data']:
            print("\n✨ Test WebSocket réussi!")
            return True
        else:
            print("\n❌ Test WebSocket échoué:")
            for key, value in test_results.items():
                if key != 'data_sample':
                    print(f"   - {key}: {value}")
            return False
    
    except Exception as e:
        print(f"❌ Erreur connexion WebSocket: {e}")
        return False
    finally:
        if sio.connected:
            sio.disconnect()


def test_collection_workflow():
    """Test du workflow de collecte globale"""
    print("\n=== Test du workflow de collecte ===\n")
    
    try:
        # 1. Démarrer la collecte
        print("1️⃣ Démarrage de la collecte globale...")
        response = requests.post(f"{BASE_URL}/api/dashboard/start-collection", json={
            'config': {
                'auto_export': False,
                'alert_notifications': True
            }
        })
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Collecte démarrée")
                session_id = data.get('session_id')
                print(f"   Session ID: {session_id}")
            else:
                print(f"❌ Échec démarrage: {data.get('message')}")
                return False
        else:
            print(f"❌ Erreur HTTP {response.status_code}")
            return False
        
        # 2. Attendre et vérifier le statut
        print("\n2️⃣ Vérification du statut après 2 secondes...")
        time.sleep(2)
        
        response = requests.get(f"{BASE_URL}/api/dashboard/summary")
        if response.status_code == 200:
            data = response.json()
            stats = data.get('global_stats', {})
            print(f"✅ Statut récupéré:")
            print(f"   - Session active: {stats.get('session_start') is not None}")
            print(f"   - Points collectés: {stats.get('data_points', 0)}")
            print(f"   - Alertes: {stats.get('total_alerts', 0)}")
        
        # 3. Arrêter la collecte
        print("\n3️⃣ Arrêt de la collecte...")
        response = requests.post(f"{BASE_URL}/api/dashboard/stop-collection")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Collecte arrêtée")
                report = data.get('report', {})
                print(f"   - Durée: {report.get('formatted_duration', 'N/A')}")
                print(f"   - Points collectés: {report.get('data_points', 0)}")
                return True
            else:
                print(f"❌ Échec arrêt: {data.get('message')}")
                return False
        else:
            print(f"❌ Erreur HTTP {response.status_code}")
            return False
    
    except Exception as e:
        print(f"❌ Erreur workflow: {e}")
        return False


def test_data_export():
    """Test de l'export des données"""
    print("\n=== Test de l'export des données ===\n")
    
    formats = ['json', 'csv', 'xlsx', 'zip']
    success_count = 0
    
    for format in formats:
        try:
            print(f"📁 Test export {format.upper()}...")
            response = requests.get(f"{BASE_URL}/api/dashboard/export/{format}")
            
            if response.status_code == 200:
                # Vérifier que c'est bien un fichier
                content_type = response.headers.get('Content-Type', '')
                content_disposition = response.headers.get('Content-Disposition', '')
                
                if 'attachment' in content_disposition:
                    print(f"✅ Export {format} réussi")
                    print(f"   Taille: {len(response.content)} octets")
                    success_count += 1
                else:
                    print(f"❌ Export {format} - pas un fichier")
            else:
                print(f"❌ Export {format} - Erreur {response.status_code}")
        
        except Exception as e:
            print(f"❌ Export {format} - Exception: {e}")
    
    print(f"\n✨ Exports réussis: {success_count}/{len(formats)}")
    return success_count > 0


def main():
    """Fonction principale de test"""
    print("🚀 Démarrage des tests du Base Home")
    print(f"📍 URL cible: {BASE_URL}")
    print(f"🕐 Heure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # Vérifier que le serveur est accessible
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("❌ Le serveur n'est pas accessible!")
            print("Assurez-vous que l'application est démarrée sur le port 3333")
            return
    except:
        print("❌ Impossible de contacter le serveur!")
        print("Démarrez l'application avec: python app.py")
        return
    
    # Exécuter les tests
    results = {
        'API': test_api_endpoints(),
        'WebSocket': test_websocket_connection(),
        'Workflow': test_collection_workflow(),
        'Export': test_data_export()
    }
    
    # Résumé
    print("\n" + "=" * 50)
    print("📊 RÉSUMÉ DES TESTS")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ RÉUSSI" if success else "❌ ÉCHOUÉ"
        print(f"{test_name:.<20} {status}")
    
    total_success = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Score final: {total_success}/{total_tests}")
    
    if total_success == total_tests:
        print("🎉 Tous les tests sont passés! Le Base est pleinement opérationnel!")
    else:
        print("⚠️ Certains tests ont échoué. Vérifiez les logs ci-dessus.")


if __name__ == "__main__":
    main()