import copy
import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
import pandas as pd

from python_service.app import create_app
from python_service.chatbot import PerfumeChatbot
from python_service.functional import clp_to_usd, compare_perfumes, usd_to_clp
from python_service.imperative import DEFAULT_MODEL, load_bundle, read_dataset

ROOT = Path(__file__).resolve().parents[1]


class FunctionalTests(unittest.TestCase):
    def test_currency_and_half_up_rounding(self):
        self.assertEqual(usd_to_clp('10.005', '100'), 1001)
        self.assertEqual(usd_to_clp('105', '950'), 99750)
        self.assertEqual(clp_to_usd(142500, 950), 150)
        for invalid in ('0', '-1', 'NaN', 'Infinity'):
            with self.assertRaises(ValueError):
                usd_to_clp(100, invalid)

    def test_filter_sort_and_no_mutation(self):
        perfumes = [{'name': 'C', 'price_usd': 30}, {'name': 'B', 'price_usd': 20}, {'name': 'A', 'price_usd': 10}]
        before = copy.deepcopy(perfumes)
        result = compare_perfumes(perfumes, 20000, 1000)
        self.assertEqual([p['name'] for p in result['items']], ['A', 'B'])
        self.assertEqual(result['items'][1]['remaining_clp'], 0)
        self.assertEqual(result, compare_perfumes(perfumes, 20000, 1000))
        self.assertEqual(perfumes, before)
        self.assertEqual(compare_perfumes(perfumes, 1000, 1000)['items'], ())
        self.assertEqual(compare_perfumes(perfumes, 30000, 1000, 'b')['total_matches'], 1)


class DatasetTests(unittest.TestCase):
    def test_supplied_dataset_has_notebook_dimensions(self):
        frame, duplicates = read_dataset(ROOT / 'python_service/data/DATASET_PROTOTIPO.csv')
        self.assertEqual(len(frame), 9911)
        self.assertEqual(frame.Perfume_Recomendado.nunique(), 236)
        self.assertEqual(duplicates, 0)

    def test_rejects_wrong_gender_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.csv'
            frame = pd.read_csv(ROOT / 'python_service/data/DATASET_PROTOTIPO.csv')
            frame.loc[0, 'Genero_Cod'] = 0
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'Genero_Cod'):
                read_dataset(path)

    def test_rejects_missing_price(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.csv'
            pd.DataFrame({'Edad': [20]}).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'Precio_Real_USD'):
                read_dataset(path)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DEFAULT_MODEL.exists():
            raise RuntimeError('Primero ejecuta npm run python:train; estas pruebas usan el modelo real.')
        cls.client = TestClient(create_app())
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def profile(self, **changes):
        return {'age': 19, 'climate': 'Frío', 'occasion': 'Oficina/Trabajo', 'gender': 'Masculino',
                'budget_clp': 142500, 'rate': '950', **changes}

    def test_health_and_notebook_prediction(self):
        self.assertEqual(self.client.get('/api/health').json()['perfume_count'], 236)
        response = self.client.post('/api/recommendations', json=self.profile())
        self.assertEqual(response.status_code, 200)
        items = response.json()['items']
        self.assertEqual([item['name'] for item in items], ['Sauvage EDP', 'Y EDP', "Terre d'Hermès"])
        self.assertEqual(items[0]['price_clp'], 99750)
        self.assertAlmostEqual(items[0]['score_percent'], 53.59, places=1)
        self.assertTrue(all(item['availability'] == 'not_verified' for item in items))

    def test_same_usd_budget_preserves_predictions_at_another_rate(self):
        a = self.client.post('/api/recommendations', json=self.profile()).json()['items']
        b = self.client.post('/api/recommendations', json=self.profile(rate='1000', budget_clp=150000)).json()['items']
        self.assertEqual([p['name'] for p in a], [p['name'] for p in b])
        self.assertEqual(b[0]['price_clp'], 105000)

    def test_unisex_supported(self):
        self.assertEqual(self.client.post('/api/recommendations', json=self.profile(gender='Unisex')).status_code, 200)

    def test_bad_inputs_rejected(self):
        for values in ({'rate': '0'}, {'rate': 'NaN'}, {'age': 0}, {'age': 19.5}, {'age': True},
                       {'gender': '0'}, {'climate': 'otro'}, {'budget_clp': -1}, {'top_n': 500}):
            with self.subTest(values=values):
                self.assertEqual(self.client.post('/api/recommendations', json=self.profile(**values)).status_code, 422)

    def test_comparison_budget_order_and_lookup(self):
        response = self.client.post('/api/compare', json={'budget_clp': 100000, 'rate': '950', 'query': 'sauvage'})
        self.assertEqual(response.status_code, 200)
        items = response.json()['items']
        self.assertTrue(items)
        self.assertTrue(all(p['price_clp'] <= 100000 for p in items))
        self.assertEqual([p['price_clp'] for p in items], sorted(p['price_clp'] for p in items))
        self.assertIn('Sauvage EDP', [p['name'] for p in items])

    def test_chat_local_price_and_source(self):
        response = self.client.post('/api/chat', json={'message': '¿Cuánto cuesta Sauvage EDP?', 'rate': '950'})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['mode'], 'local_retrieval')
        self.assertIn('$99.750 CLP', body['answer'])
        self.assertIn('Precio_Real_USD', body['sources'][0])

    def test_chat_context(self):
        body = self.client.post('/api/chat', json={'message': '¿Y su precio?', 'rate': '950',
            'history': [{'role': 'user', 'content': 'Sauvage EDP'}]}).json()
        self.assertIn('Sauvage EDP: $99.750 CLP', body['answer'])

    def test_chat_recommender_question(self):
        body = self.client.post('/api/chat', json={'message': '¿Cómo funciona el recomendador?'}).json()
        self.assertIn('Encuentra tu perfume', body['answer'])

    def test_chat_unknown_does_not_invent_price(self):
        body = self.client.post('/api/chat', json={'message': '¿Cuánto cuesta PerfumeInexistenteXYZ?', 'rate': '950'}).json()
        self.assertNotIn('$', body['answer'])
        unknown = self.client.post('/api/chat', json={'message': '¿Cuál es la capital de Francia?'}).json()
        self.assertFalse(unknown['matched'])
        self.assertEqual(self.client.post('/api/chat', json={'message': '   '}).status_code, 422)

    def test_page_and_security_headers(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Encuentra tu perfume', response.text)
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)

    def test_missing_model_is_explicit_and_faq_keeps_working(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(Path(directory) / 'missing.joblib')) as client:
                self.assertEqual(client.get('/api/health').json()['model_status'], 'missing')
                self.assertEqual(client.post('/api/recommendations', json=self.profile()).status_code, 503)
                self.assertEqual(client.post('/api/chat', json={'message': 'hola'}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
