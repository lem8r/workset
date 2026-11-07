# -*- coding: utf-8 -*-
"""Тести «Умов клієнтів» (М3, К1): Odoo.sh запускає їх на dev-збірці (локально: odoo-bin -i workset_client --test-enable --test-tags
workset_client). Усі дані — вигадані в самому тесті («Customer K1», «Line K1»; числа не збігаються з даними штабу); «сьогодні» —
31.03.2030 (даних копії в 2030 немає); посередники «Ставок» підмінені порожніми — тест не залежить від домовленостей бази.

Сценарій:
- лінія Line K1, замовник Customer K1 (у «Замовниках» лінії) з контактами Contact K1a / K1b; дві діючі ставки двох працівників —
  «Хто знайшов»: «ми» і не вказано;
- загальна ставка лінії: мінімум частки 3, оренда авто 0,5; житло — правило лінії (платимо ми з буфера);
- «Хто платить» паливо: правило лінії — ми, правило замовника — партнер (замовник точніший); перевезення — правила немає;
- картка DKV на лінію; рядки «лінія × місяць» лютого (10 год) і березня (5 год) 2030 — для «Місяць | Квартал»."""
import re
from contextlib import ExitStack
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.workset_rates.models import agent_deals

from ..models import calc

M_LAST = '2030-03-31'
JAN = '2030-01-01'
FEB = '2030-02-01'
MAR = '2030-03-01'
OLD = '2029-01-01'
PAY_KEYS = ['housing', 'transport', 'fuel', 'tool', 'auto', 'car_rent', 'fund']


@tagged('post_install', '-at_install')
class TestWorksetClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.eur = env.ref('base.EUR')
        cls.eur.active = True
        cls.co = env['res.company'].create({'name': 'Test firm K1', 'currency_id': cls.eur.id})
        cls.env = env(context=dict(env.context, allowed_company_ids=[cls.co.id, env.company.id], rates_today=M_LAST, profit_today=M_LAST))
        env = cls.env
        # правила бонусів бази (порожні «Замовники» — усі) дали б тестовим ставкам свій бонус
        env['workset.office.bonus'].sudo().search([]).write({'active': False})
        Partner = env['res.partner']
        cls.Partner = Partner
        cls.cust = Partner.create({'name': 'Customer K1', 'is_company': True})
        cls.contact_a = Partner.create({'name': 'Contact K1a', 'parent_id': cls.cust.id})
        cls.contact_b = Partner.create({'name': 'Contact K1b', 'parent_id': cls.cust.id})
        cls.other = Partner.create({'name': 'Company K1 other', 'is_company': True})
        cls.line = env['workset.line'].create({'name': 'Line K1', 'customer_ids': [(6, 0, [cls.cust.id])]})
        cls.rule = env['workset.rate.rule'].create({'line_id': cls.line.id, 'anchor': 'markup', 'share_line_found': 4, 'share_we_found': 5,
                                                    'min_share': 3, 'car_rent': 0.5, 'date_from': OLD, 'source': 'owner',
                                                    'source_note': 'test rule'})
        cls.housing = env['workset.line.housing'].create({'line_id': cls.line.id, 'kind': 'payment_buffer', 'payer': 'we_buffer',
                                                          'date_from': OLD, 'source': 'owner', 'source_note': 'test housing'})
        Cost = env['workset.line.cost.rule']
        cls.fuel_line = Cost.create({'line_id': cls.line.id, 'kind': 'fuel', 'payer': 'we', 'date_from': OLD, 'note': 'line fuel'})
        cls.fuel_cust = Cost.create({'line_id': cls.line.id, 'customer_id': cls.cust.id, 'kind': 'fuel', 'payer': 'partner',
                                     'date_from': '2029-06-01', 'note': 'customer fuel'})
        cls.card = env['workset.dkv.card'].create({'number': 'TEST-K1-CARD', 'seq': 1,
                                                   'period_ids': [(0, 0, {'target': 'line', 'line_id': cls.line.id, 'date_from': OLD})]})
        Emp = env['hr.employee'].with_company(cls.co)
        cls.e1, cls.e2 = [Emp.create({'name': 'Worker K1 %d' % i, 'company_id': cls.co.id}) for i in (1, 2)]
        Rate = env['workset.rate']
        with cls._deals():
            cls.r1 = Rate.create({'person_id': cls.e1.work_contact_id.id, 'customer_id': cls.cust.id, 'found_by': 'us', 'wage': 14,
                                  'source': 'other', 'date_from': OLD})
            cls.r2 = Rate.create({'person_id': cls.e2.work_contact_id.id, 'customer_id': cls.cust.id, 'wage': 16, 'source': 'other',
                                  'date_from': OLD})
        # рядки «лінія × місяць» пише перерахунок «Прибутковості»; тут — готові, щоб перевірити лише підсумок періоду картки
        Month = env['workset.profit.month'].sudo()
        for month, hours, share, housing, net in ((JAN, 5, 20, 0, 20), (FEB, 10, 60, -10, 50), (MAR, 5, 40, 0, 40)):
            Month.create({'month': month, 'row_kind': 'line', 'line_id': cls.line.id, 'name': 'Line K1', 'hours_total': hours,
                          'hours_rate': hours, 'share': share, 'housing': housing, 'net': net})

    @classmethod
    def _deals(cls):
        # посередників і агентів людей «Ставок» немає — частки ставок не залежать від домовленостей бази
        stack = ExitStack()
        stack.enter_context(patch.object(agent_deals, 'read_deals', return_value=[]))
        stack.enter_context(patch.object(agent_deals, 'read_people', return_value=[]))
        return stack

    def _user(self, login, groups):
        # користувачу — обидві фірми тесту (записи класу створено у фірмі cls.co; без неї «Access to unauthorized or invalid companies»)
        return new_test_user(self.env, login=login, groups=groups, company_ids=[(6, 0, [self.env.ref('base.main_company').id, self.co.id])])

    def _as(self, rec, user):
        # фірми контексту класу — не для користувача: лише його фірми, власна — перша (як у тестах «Прибутковості»)
        ids = [user.company_id.id] + [i for i in user.company_ids.ids if i != user.company_id.id]
        return rec.with_user(user).with_context(allowed_company_ids=ids)

    # ——— екран: рядки й описи кліку ———
    def test_screen_rows_and_opens(self):
        data = self.Partner.workset_client_card(self.contact_a.id)
        p = data['partner']
        self.assertEqual(p['id'], self.cust.id, 'контакт замовника — картка його фірми (комерційний контрагент)')
        self.assertEqual([x['name'] for x in p['lines']], ['Line K1'])
        m = data['money']
        self.assertEqual(m['count'], 2)
        self.assertEqual((m['price']['min'], m['price']['max']), (min(self.r1.price, self.r2.price), max(self.r1.price, self.r2.price)))
        self.assertEqual((m['wage']['min'], m['wage']['max']), (14, 16))
        self.assertAlmostEqual(m['share'], round((self.r1.our_share + self.r2.our_share) / 2, 2))
        self.assertEqual(m['min_share'], 3, 'мінімум — із загальної ставки лінії × замовника')
        self.assertEqual((m['rule_open']['model'], m['rule_open']['res_id']), ('workset.rate.rule', self.rule.id))
        self.assertEqual(m['open']['model'], 'workset.rate')
        self.assertIn(('state', '=', 'current'), m['open']['domain'])
        self.assertIsNone(m['withdraw'], 'відсотка за виведення немає — «—», не 0')

        self.assertEqual([r['key'] for r in data['pays']], [k for k in PAY_KEYS if k != 'fund'], 'К1г п. 5: «Фонд працівників — не діє» не показується')
        pays = {r['key']: r for r in data['pays']}
        self.assertEqual(pays['housing']['source_text'], 'правило лінії Line K1', 'К1г п. 2: коротко «правило лінії <лінія>», дата — у колонці «З якого числа»')
        self.assertEqual(pays['tool']['source_text'], '', 'правила немає — пусто')
        self.assertEqual(pays['fuel']['source_text'], 'правило замовника')
        self.assertEqual(pays['fuel']['source'], 'customer fuel', 'повний текст правила — для підказки')
        h = pays['housing']
        labels = dict(self.env['workset.line.housing']._fields['payer']._description_selection(self.env))
        self.assertEqual((h['payer'], h['level'], h['tone']), (labels['we_buffer'], 'line', ''))
        self.assertEqual((h['open']['model'], h['open']['res_id']), ('workset.line.housing', self.housing.id), 'житло — форма правила лінії')
        fuel = pays['fuel']
        self.assertEqual(fuel['open']['res_id'], self.fuel_cust.id, 'правило замовника точніше за правило лінії')
        self.assertEqual((fuel['level'], fuel['source']), ('customer', 'customer fuel'))
        self.assertEqual(fuel['cards'], [self.card.display_name])
        self.assertEqual(fuel['cards_open']['domain'], [('id', 'in', [self.card.id])])
        tr = pays['transport']
        self.assertEqual(tr['tone'], 'muted', 'правила немає — «Ми (правила немає)» сірим')
        self.assertNotIn('res_id', tr['open'])
        self.assertEqual(tr['open']['domain'], [('line_id', '=', self.line.id), ('kind', '=', 'transport')])
        self.assertEqual((pays['car_rent']['amount'], pays['car_rent']['open']['res_id']), (0.5, self.rule.id))
        self.assertNotIn('fund', pays, 'фонду немає — рядка немає')

        a = data['agent']
        self.assertEqual((a['found']['us'], a['found']['line'], a['found']['none'], a['found']['total']), (1, 0, 1, 2))
        self.assertTrue(a['found']['missing'], '«не вказано у 1 з 2» — жовтим')
        self.assertIn(('found_by', '=', False), a['missing_open']['domain'])
        self.assertEqual(a['installed'], 'workset.agent.deal.client' in self.env, 'агенти — м\'яко: моделі немає — «не встановлено»')
        self.assertEqual(a['items'], [])

    # ——— «Договір і оплата»: порожнє — жовте, «Заповнити», «Позначити перевіреним» ———
    def test_contract_empty_yellow_then_fill_and_check(self):
        editor = self._user('ws_client_editor', 'base.group_user,workset_client.group_editor')
        Card = self._as(self.Partner, editor)
        data = Card.workset_client_card(self.cust.id)
        items = {i['key']: i for i in data['contract']['items']}
        self.assertEqual(list(items), ['contract', 'scan', 'payment_term', 'withdraw', 'sign', 'site_contact', 'site_address', 'note'])
        self.assertTrue(all(i['empty'] for i in items.values()), 'порожні поля договору — жовті ознаки (і «Відсоток за виведення» — «не внесено»)')
        self.assertEqual(data['contract']['missing'], 8)
        self.assertTrue(items['contract']['empty_text'] and items['payment_term']['empty_text'])
        self.assertFalse(data['partner']['checked']['ok'], 'не перевірено — жовтий чип')
        self.assertTrue(data['can_edit'])

        # свій строк оплати без фірми (рядок «100 % одразу» Odoo ставить сам) — не залежить від строків бази
        term = self.env['account.payment.term'].create({'name': 'Test term K1'})
        wizard = self._as(self.env['workset.client.terms'], editor).with_context(default_partner_id=self.cust.id).create({
            'contract_no': 'K1-2030', 'contract_date': '2030-01-15', 'sign_id': self.contact_a.id, 'site_contact_id': self.contact_b.id,
            'site_address': 'Test street K1', 'withdraw_pct': 2.5, 'note': 'test note', 'payment_term_id': term.id})
        self.assertEqual(wizard.partner_id, self.cust, 'вікно — для замовника з контексту')
        wizard.action_save()
        self._as(self.cust, editor).workset_client_mark_checked()
        data = Card.workset_client_card(self.cust.id)
        items = {i['key']: i for i in data['contract']['items']}
        self.assertEqual(data['contract']['missing'], 1, 'лишився лише скан')
        self.assertTrue(items['scan']['empty'])
        self.assertIn('K1-2030', items['contract']['value'])
        self.assertIn('15.01.2030', items['contract']['value'])
        self.assertEqual(items['payment_term']['value'], '%s: %s' % (editor.company_id.name, term.display_name),
                         'строк оплати — стандартне поле контакту; лише фірма, де він заданий (без «—» для решти)')
        self.assertEqual((items['sign']['value'], items['site_contact']['value']), ('Contact K1a', 'Contact K1b'))
        self.assertEqual(data['money']['withdraw'], 2.5)
        self.assertEqual(items['withdraw']['value'], '2,5 %')
        self.assertTrue(data['partner']['checked']['ok'])
        self.assertEqual(data['partner']['checked']['who'], editor.name)
        self.assertEqual(self.cust.sudo().workset_client_checked_by_id, editor)

    # ——— «Картка лінії ›» — лише групі «Прибутковість: Перегляд» ———
    def test_line_link_only_profit_viewer(self):
        plain = self._user('ws_client_plain', 'base.group_user')
        profit = self._user('ws_client_profit', 'base.group_user,workset_profit.group_viewer')
        self.assertTrue(plain.has_group('workset_client.group_viewer'), 'на час збирання «Перегляд» — у кожного внутрішнього користувача')
        d_plain = self._as(self.Partner, plain).workset_client_card(self.cust.id)
        d_profit = self._as(self.Partner, profit).workset_client_card(self.cust.id)
        self.assertFalse(d_plain['profit']['link'], 'без групи «Прибутковості» — без посилання «Картка лінії»')
        self.assertEqual(d_profit['profit']['link']['line_id'], self.line.id)
        self.assertEqual(d_plain['money']['count'], 2, 'цифри — sudo: «всі, з часткою» на час збирання')
        self.assertFalse(d_plain['money']['open'], 'відкрити ставки — лише за правами самого користувача')
        self.assertFalse(d_plain['can_edit'])

    # ——— «Що з цього виходить»: Місяць | Квартал ———
    def test_profit_period_month_and_quarter(self):
        d = self.Partner.workset_client_card(self.cust.id)
        self.assertEqual(d['period']['months'], [FEB], 'за замовчуванням — останній закритий місяць')
        rows = {r['key']: r for r in d['profit']['rows']}
        self.assertEqual((rows['share']['ph'], rows['housing']['ph'], rows['net']['ph']), (6.0, -1.0, 5.0))
        q = self.Partner.workset_client_card(self.cust.id, 'quarter', FEB)
        self.assertEqual(q['period']['months'], [JAN, FEB], 'К1б п. 4: квартал — до останнього закритого місяця, неповного березня немає')
        rows = {r['key']: r for r in q['profit']['rows']}
        self.assertEqual(rows['share']['amount'], 80)
        self.assertEqual(rows['share']['ph'], round(80 / 15.0, 2), 'на години зі ставкою всього періоду, не середнє місяців')
        self.assertEqual(rows['net']['ph'], round(70 / 15.0, 2))
        self.assertEqual(q['profit']['open']['domain'], [('month', 'in', [JAN, FEB]), ('row_kind', '=', 'line'), ('line_id', '=', self.line.id)])
        self.assertFalse(q['period']['next'], 'наступний квартал — поза останнім закритим місяцем')
        if 'remain' in self.env['workset.profit.month']._fields:
            self.assertTrue(q['profit']['oh_missing'], 'місяці без «ZUS і загальні» — «не перераховано», а не 0')
            self.assertNotIn('remain', rows)

    # ——— права ———
    def test_rights_viewer_editor(self):
        clerk = self._user('ws_client_clerk', 'base.group_user,base.group_partner_manager')
        portal = self._user('ws_client_portal', 'base.group_portal')
        editor = self._user('ws_client_editor2', 'base.group_user,workset_client.group_editor')
        with self.assertRaises(AccessError):
            self._as(self.cust, clerk).write({'workset_client_contract_no': 'K1-X'})
        self._as(self.cust, clerk).write({'comment': 'test comment K1'})  # інші поля контакту — як і раніше
        with self.assertRaises(AccessError):
            self._as(self.cust, clerk).workset_client_mark_checked()
        with self.assertRaises(AccessError):
            self._as(self.env['workset.client.terms'], clerk).create({'partner_id': self.cust.id})
        with self.assertRaises(AccessError):
            self._as(self.Partner, portal).workset_client_card(self.cust.id)
        self._as(self.cust, editor).workset_client_mark_checked()
        self.assertTrue(self.cust.sudo().workset_client_checked_date)
        self.assertFalse(self.cust.sudo().workset_client_contract_no, 'правку без групи не записано')

    # ——— список «Умови клієнтів» ———
    def test_list_customers_and_columns(self):
        ids = self.Partner.search([('workset_client_is_customer', '=', True)]).ids
        self.assertIn(self.cust.id, ids)
        self.assertNotIn(self.other.id, ids)
        c = self.cust
        self.assertEqual((c.workset_client_line_text, c.workset_client_rate_count), ('Line K1', 2))
        self.assertFalse(c.workset_client_has_contract)
        self.assertTrue(c.workset_client_contract_text and c.workset_client_term_text and c.workset_client_checked_text)
        labels = dict(self.env['workset.line.housing']._fields['payer']._description_selection(self.env))
        self.assertEqual(c.workset_client_housing_text, labels['we_buffer'])
        act = c.action_workset_client_card()
        self.assertEqual((act['tag'], act['params']), ('workset_client.card', {'partner_id': c.id}))

    # ——— «Останні зміни» ———
    def test_changes_tracking_and_rule_creation(self):
        # причина падіння dev-збірки 07.11: замовник створений у setUpClass, а mail.thread.create ставить йому _track_discard (початкові
        # значення None) до першого precommit — доки той не відпрацював, write тієї ж транзакції не трекається (так у Odoo, не помилка
        # модуля). Скидаємо чергу precommit, як це зробив би коміт між створенням і правкою
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.cust.write({'workset_client_contract_no': 'K1-A'})
        self.env.flush_all()
        self.env.cr.precommit.run()
        d = self.Partner.workset_client_card(self.cust.id)
        self.assertLessEqual(len(d['changes']), calc.CHANGES_MAX)
        self.assertEqual([c['at'] for c in d['changes']], sorted((c['at'] for c in d['changes']), reverse=True), 'найсвіжіші — першими')
        # усі події до обрізання (у тій самій секунді їх може бути більше десяти — порядок між ними не перевіряємо)
        with patch.object(calc, 'changes_top', side_effect=lambda items, limit=calc.CHANGES_MAX, lang='uk': items):
            full = self.Partner.workset_client_card(self.cust.id)['changes']
        own = [c for c in full if c['new'] == 'K1-A']
        self.assertEqual(len(own), 1, 'трекінг свого поля — «було → стало»')
        self.assertEqual(own[0]['old'], '—')
        self.assertIn('Номер договору', own[0]['what'])
        self.assertTrue(any(c['open'] and c['open']['model'] == 'workset.line.housing' and c['open'].get('res_id') == self.housing.id for c in full),
                        'створення правила житла лінії')
        self.assertTrue(any(c['open'] and c['open']['model'] == 'workset.dkv.card.period' for c in full), 'період картки DKV лінії')

    # ═══ К1б ═══
    def _settle(self):
        # записи setUpClass ще «в створенні» (mail.thread: _track_discard до першого precommit) — без цього їхні правки не трекаються
        self.env.flush_all()
        self.env.cr.precommit.run()

    def _wizard(self, user, **vals):
        return self._as(self.env['workset.client.terms'], user).with_context(default_partner_id=self.cust.id).create(vals)

    # Б1: перепривʼязка чужих вкладень
    def test_scan_save_moves_own_attachment_and_tracks(self):
        self._settle()
        editor = self._user('ws_client_scan_editor', 'base.group_user,workset_client.group_editor')
        Att = self.env['ir.attachment']
        mine = Att.with_user(editor).create({'name': 'k1b-scan-own.txt', 'raw': b'x', 'res_model': 'workset.client.terms', 'res_id': 0})
        self._wizard(editor, scan_ids=[(6, 0, [mine.id])]).action_save()
        self.assertEqual(self.cust.sudo().workset_client_contract_scan_ids, mine)
        self.assertEqual((mine.sudo().res_model, mine.sudo().res_id), ('res.partner', self.cust.id), 'свій новий скан переїхав до замовника')
        self._settle()
        tv = self.env['mail.tracking.value'].sudo().search([
            ('mail_message_id.model', '=', 'res.partner'), ('mail_message_id.res_id', '=', self.cust.id),
            ('field_id.name', '=', 'workset_client_contract_scan_ids')])
        self.assertTrue(tv, 'трекінг Many2many «Скан договору»')
        self.assertIn('k1b-scan-own.txt', tv[0].new_value_char)

    def test_scan_save_ignores_foreign_attachments(self):
        # Б1. Чужий файл не стає сканом замовника ні за яких прав: ORM сам не дає звичайному редактору записати чужий файл у scan_ids
        # (AccessError — прийнятний результат); редактор із правом правити контакти доходить до «Зберегти» — там відсікає _own_scans
        Att = self.env['ir.attachment'].sudo()
        foreign = Att.create({'name': 'k1b-foreign.txt', 'raw': b'y', 'res_model': 'res.partner', 'res_id': self.other.id})
        stranger = Att.create({'name': 'k1b-stranger.txt', 'raw': b'z', 'res_model': 'workset.client.terms', 'res_id': 0})  # створив не editor
        # Спроба в try: AccessError від ORM — прийнятно; ORM пропустив — тоді обовʼязково відсікає _own_scans. Утвердження нижче — в обох випадках
        for login, groups in (('ws_client_scan_editor2', 'base.group_user,workset_client.group_editor'),
                              ('ws_client_scan_editor3', 'base.group_user,workset_client.group_editor,base.group_partner_manager')):
            editor = self._user(login, groups)
            try:
                wizard = self._wizard(editor, scan_ids=[(6, 0, [foreign.id, stranger.id])])
                wizard.action_save()
            except AccessError:
                pass  # ORM зупинив раніше за наш код — теж закрито
            self.assertFalse(self.cust.sudo().workset_client_contract_scan_ids, '%s: чужі вкладення не стали сканами замовника' % login)
            self.assertEqual((foreign.res_model, foreign.res_id), ('res.partner', self.other.id), '%s: чужий файл не перепривʼязано' % login)
            self.assertEqual((stranger.res_model, stranger.res_id), ('workset.client.terms', 0), login)

    # Б2: default_get лише редактору
    def test_default_get_only_editor(self):
        clerk = self._user('ws_client_dg_clerk', 'base.group_user')
        editor = self._user('ws_client_dg_editor', 'base.group_user,workset_client.group_editor')
        self.cust.sudo().write({'workset_client_contract_no': 'K1-DG'})
        Wiz = self.env['workset.client.terms']
        with self.assertRaises(AccessError):
            self._as(Wiz, clerk).with_context(default_partner_id=self.cust.id).default_get(['contract_no'])
        got = self._as(Wiz, editor).with_context(default_partner_id=self.cust.id).default_get(['contract_no'])
        self.assertEqual(got['contract_no'], 'K1-DG')

    # п. 3: строк оплати по фірмах
    def test_payment_term_per_company(self):
        term = self.env['account.payment.term'].create({'name': 'Test term K1b'})
        self.cust.sudo().with_company(self.co).property_payment_term_id = term
        t = self.Partner._workset_client_terms(self.cust)
        self.assertTrue(t['any'])
        self.assertIn('%s: %s' % (self.co.name, term.display_name), t['text'])
        self.assertEqual(t['text'], '%s: %s' % (self.co.name, term.display_name), 'лише фірми, де строк заданий, без порожніх «—»')
        self.assertIn(self.cust.id, self.Partner.search([('workset_client_has_term', '=', True)]).ids, '«є хоча б в одній фірмі»')
        self.assertNotIn(self.cust.id, self.Partner.search([('workset_client_has_term', '=', False)]).ids)
        self.assertIn(self.other.id, self.Partner.search([('workset_client_has_term', '=', False)]).ids)
        self.assertTrue(self.cust.workset_client_has_term)
        items = {i['key']: i for i in self.Partner.workset_client_card(self.cust.id)['contract']['items']}
        self.assertFalse(items['payment_term']['empty'])
        self.assertIn(term.display_name, items['payment_term']['value'])
        # майстер працює у фірмі контексту: запускаємо його саме у перевірюваній фірмі
        wizard = self.env['workset.client.terms'].with_company(self.co).with_context(default_partner_id=self.cust.id).create({})
        self.assertIn(self.co.name, wizard.company_note, 'у «Заповнити» — «для фірми X»')

    # п. 4, п. 10: періоди «Рік» і «Квартал» — до останнього закритого місяця
    def test_period_year_and_quarter_stop_at_last_closed(self):
        y = self.Partner.workset_client_card(self.cust.id, 'year', FEB)
        self.assertEqual((y['period']['kind'], y['period']['months']), ('year', [JAN, FEB]))
        self.assertEqual(y['period']['value'], JAN)
        rows = {r['key']: r for r in y['profit']['rows']}
        self.assertEqual(rows['share']['amount'], 80, 'березень (поточний, неповний) у «Рік» не входить')
        q = self.Partner.workset_client_card(self.cust.id, 'quarter', MAR)
        self.assertEqual(q['period']['months'], [JAN, FEB], 'якір у поточному місяці — як останній закритий')
        m = self.Partner.workset_client_card(self.cust.id, 'month', MAR)
        self.assertEqual(m['period']['months'], [MAR], '«Місяць» явно — поточний місяць можна')

    # п. 5: посередник у ставках — поле є, нульове — порожньо
    def test_agent_in_rates_key(self):
        a = self.Partner.workset_client_card(self.cust.id)['agent']
        self.assertIn('in_rates', a)
        self.assertFalse(a['in_rates'], 'частка посередника в ставках нуль — рядка немає')
        # ненульовий: поле «Посередник» ставки пише «Ставки» (readonly, ланцюжок) — для проби ставимо SQL-ом, без перерахунку ланцюжка
        self.env.cr.execute('UPDATE workset_rate SET agent_client_share = 1.5 WHERE id = %s', [self.r1.id])
        self.r1.invalidate_recordset(['agent_client_share'])
        a = self.Partner.workset_client_card(self.cust.id)['agent']
        self.assertEqual(a['in_rates'], {'min': 1.5, 'max': 1.5, 'n': 1}, 'посередник у ставках: лише додатні, одна ставка з двох')
        self.assertEqual(a['in_rates_open']['model'], 'workset.rate')
        self.assertIn(('agent_client_share', '>', 0), a['in_rates_open']['domain'])

    # п. 6, 7: кілька ліній і «мінімум» за замовчуванням
    def test_multiple_lines_pick_and_min_default(self):
        Line = self.env['workset.line']
        c3 = self.Partner.create({'name': 'Customer K1c', 'is_company': True})
        l2 = Line.create({'name': 'Line K1c-2', 'customer_ids': [(6, 0, [c3.id])]})
        l3 = Line.create({'name': 'Line K1c-3', 'customer_ids': [(6, 0, [c3.id])]})
        d = self.Partner.workset_client_card(c3.id)
        p = d['partner']
        self.assertEqual((p['more'], len(p['pick'])), (1, 2), '«ще 1 ліній ›» і вибір з двох')
        self.assertEqual(len(p['lines']), 1, 'у шапці — обрана лінія')
        self.assertEqual(p['line_id'], d['profit']['line']['id'])
        other = l3 if p['line_id'] == l2.id else l2
        d2 = self.Partner.workset_client_card(c3.id, None, None, other.id)
        self.assertEqual((d2['partner']['line_id'], d2['profit']['line']['id']), (other.id, other.id))
        d3 = self.Partner.workset_client_card(c3.id, None, None, self.line.id)
        self.assertEqual(d3['partner']['line_id'], p['line_id'], 'чужа лінія ігнорується')
        # «Мінімум частки»: правила пари немає — параметр «Ставок» (сірим), немає й його — «не задано»
        Param = self.env['ir.config_parameter'].sudo()
        Param.set_param('workset_rates.min_share_default', '2.5')
        m = self.Partner.workset_client_card(c3.id)['money']
        self.assertEqual((m['min_share'], m['min_default']), (None, 2.5))
        Param.set_param('workset_rates.min_share_default', False)
        m = self.Partner.workset_client_card(c3.id)['money']
        self.assertEqual((m['min_share'], m['min_default']), (None, None))
        m = self.Partner.workset_client_card(self.cust.id)['money']
        self.assertEqual((m['min_share'], m['min_default']), (3, None), 'у правилі мінімум є — параметр не потрібен')

    # п. 6, п. 10: замовник, відомий лише зі ставок, — колонки «Лінія» і «Житло»
    def test_list_customer_known_only_by_rates(self):
        c4 = self.Partner.create({'name': 'Customer K1d', 'is_company': True})
        e3 = self.env['hr.employee'].with_company(self.co).create({'name': 'Worker K1d', 'company_id': self.co.id})
        with self._deals():
            rate = self.env['workset.rate'].create({'person_id': e3.work_contact_id.id, 'customer_id': c4.id, 'line_id': self.line.id,
                                                    'wage': 15, 'source': 'other', 'date_from': OLD})
        if rate.line_id != self.line:
            self.skipTest('лінія ставки виводиться самою «Ставкою» — перевірити на копії')
        self.assertIn(c4.id, self.Partner.search([('workset_client_is_customer', '=', True)]).ids)
        self.assertEqual(c4.workset_client_line_text, 'Line K1', 'колонка «Лінія» — лінія його ставок')
        labels = dict(self.env['workset.line.housing']._fields['payer']._description_selection(self.env))
        self.assertEqual(c4.workset_client_housing_text, labels['we_buffer'], 'колонка «Житло» — за лінією ставок')
        self.assertEqual(self.Partner.workset_client_card(c4.id)['partner']['line_id'], self.line.id)

    # п. 8: обʼєднання контактів не-редактором
    def test_merge_context_key_is_not_a_bypass(self):
        # контекст у call_kw задає сам клієнт RPC — жодний ключ контексту не обходить групу (дірку знайшла приймання К1б)
        clerk = self._user('ws_client_merge_clerk', 'base.group_user,base.group_partner_manager')
        with self.assertRaises(AccessError):
            self._as(self.cust, clerk).write({'workset_client_terms_note': 'K1-merge'})
        for key in ('workset_client_merge', 'merge', 'tracking_disable'):
            with self.assertRaises(AccessError):
                self._as(self.cust, clerk).with_context(**{key: True}).write({'workset_client_terms_note': 'K1-merge'})
        with self.assertRaises(AccessError):
            self._as(self.Partner, clerk).with_context(workset_client_merge=True).create({'name': 'Merge ctx K1b', 'workset_client_terms_note': 'x'})
        self.assertFalse(self.cust.sudo().workset_client_terms_note)

    def test_real_partner_merge_wizard_by_non_editor(self):
        Wiz = self.env.get('base.partner.merge.automatic.wizard')
        if Wiz is None:
            self.skipTest("майстра обʼєднання контактів у базі немає")
        clerk = self._user('ws_client_merge_clerk2', 'base.group_user,base.group_partner_manager')
        src = self.Partner.create({'name': 'Merge src K1b', 'is_company': True})
        dst = self.Partner.create({'name': 'Merge dst K1b', 'is_company': True})
        src.sudo().write({'workset_client_terms_note': 'K1-from-src'})
        self._as(Wiz, clerk)._merge([src.id, dst.id], dst.with_user(clerk), extra_checks=False)  # без AccessError на workset_client_*
        self.assertFalse(src.exists(), 'слияние выполнено: источник удалён')
        # _update_values (Odoo 19) переносит только поля с copy=True, а наши — copy=False: поддельное «Перевірено» слиянием в настоящего
        # заказчика не попадёт (К1в п. 8: «значение перешло» невозможно по устройству — проверяем, что и не перешло)
        self.assertFalse(dst.sudo().workset_client_terms_note)

    # К1в п. 1: свої поля не підставляються default_<поле> з контексту / ir.default (create, name_create, copy)
    def test_forged_defaults_rejected_for_non_editor(self):
        clerk = self._user('ws_client_forge_clerk', 'base.group_user,base.group_partner_manager')
        Clerk = self._as(self.Partner, clerk)
        forged = (('default_workset_client_checked_date', '2030-01-01'), ('default_workset_client_checked_by_id', clerk.id),
                  ('default_workset_client_contract_no', 'K1-FORGED'))
        # контроль: без default_* ті самі дії не-редактору дозволені — отже AccessError нижче саме від перевірки модуля
        Clerk.create({'name': 'Forged K1v control'})
        Clerk.name_create('Forged K1v control name')
        self._as(self.cust, clerk).copy()
        for key, value in forged:
            ctx = {key: value}
            with self.assertRaises(AccessError, msg='create ' + key):
                Clerk.with_context(**ctx).create({'name': 'Forged K1v'})
            with self.assertRaises(AccessError, msg='name_create ' + key):
                Clerk.with_context(**ctx).name_create('Forged K1v name')
            with self.assertRaises(AccessError, msg='copy ' + key):
                self._as(self.cust, clerk).with_context(**ctx).copy()
        self.env['ir.default'].sudo().set('res.partner', 'workset_client_contract_no', 'K1-IRD')
        with self.assertRaises(AccessError, msg='ir.default'):
            Clerk.create({'name': 'Forged K1v ir.default'})
        self.assertFalse(self.Partner.sudo().search([('name', 'like', 'Forged K1v'), ('workset_client_contract_no', '!=', False)]),
                         'поддельных контактов не осталось')
        # редактору те самі default_* дозволені
        editor = self._user('ws_client_forge_editor', 'base.group_user,workset_client.group_editor,base.group_partner_manager')
        rec = self._as(self.Partner, editor).with_context(default_workset_client_checked_date='2030-01-01').create({'name': 'Forged K1v editor'})
        self.assertEqual(str(rec.sudo().workset_client_checked_date), '2030-01-01')

    # ═══ К1г ═══
    def test_changes_collapse_same_kind(self):
        # два правила житла замовника (періоди не перетинаються) + правило лінії з setUpClass: однотипні «створено» одного автора за день —
        # один рядок «Житло: правило створено — N змін»
        Housing = self.env['workset.line.housing']
        for date_from, date_to in (('2029-02-01', '2029-02-28'), ('2029-03-01', '2029-03-31')):
            Housing.create({'line_id': self.line.id, 'customer_id': self.cust.id, 'kind': 'payment_buffer', 'payer': 'we_buffer',
                            'date_from': date_from, 'date_to': date_to, 'source': 'owner', 'source_note': 'test housing K1g'})
        rows = self.Partner.workset_client_card(self.cust.id)['changes']
        groups = [c for c in rows if c['count'] > 1 and 'Житло' in c['what']]
        self.assertTrue(groups, 'однотипні зміни згорнуті в один рядок')
        g = groups[0]
        self.assertGreaterEqual(g['count'], 3)
        self.assertEqual(len(g['items']), g['count'])
        self.assertRegex(g['count_text'], r'^\d+ змін[иа]?$')
        self.assertTrue(all(i['open'] and i['open']['model'] == 'workset.line.housing' for i in g['items']), 'кожна зміна в списку відкривається')
        self.assertFalse(g['open'], 'у згорнутого рядка немає свого кліку — клік розкриває список')
        self.assertFalse(any(re.search(r'\d{4}-\d{2}-\d{2}', i['record'] or '') for c in rows for i in c['items'] + [c]),
                         'у назвах записів теж ДД.ММ.РРРР')

    def test_list_missing_and_no_line(self):
        c = self.cust
        self.assertEqual(c.workset_client_missing_text, 'договір, термін, перевірка', 'нічого немає — три пункти')
        self.assertTrue(c.workset_client_has_line)
        editor = self._user('ws_client_missing_editor', 'base.group_user,workset_client.group_editor')
        self._as(c, editor).workset_client_mark_checked()
        c.sudo().write({'workset_client_contract_no': 'K1G-1'})
        c.invalidate_recordset()
        self.assertEqual(c.workset_client_missing_text, 'термін', 'договір і перевірка є — лишається термін')
        lonely = self.Partner.create({'name': 'Customer K1g lonely', 'is_company': True})
        self.assertFalse(lonely.workset_client_has_line)
        self.assertEqual(lonely.workset_client_line_text, 'без лінії')
