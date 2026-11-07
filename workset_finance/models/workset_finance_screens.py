# -*- coding: utf-8 -*-
"""Екран «Власник» (Фінанси, круг 2; макет A + таблиця макета B під ним, слово власника 07.11 «макет: A + таблиця B нижче»): client action
workset_finance.owner (static/src/js/finance_screens.js) — ОДИН виклик сервера finance_owner(period) (круг 3: період — місяць, рік чи свій
від місяця до місяця; старий виклик finance_owner(month) — місяць).

Числа — збережений «місяць драбини» (workset.finance.month — його пише перерахунок), деталі — «Рядки» (workset.finance.item) того самого
перерахунку, поправки й звірка — свої моделі: нічого не рахується наново з книг і нічого не пишеться. Плитки, «з початку року», водоспад, ряд
року, таблицю й формат «тис. €» рахують чисті функції models/calc.py. Кожне число віддається з описом списку для кліку ('open': модель,
заголовок, домен, контекст без «Створити»; res_id — форма одного запису) — екран лише виконує його (як «Прибутковість», М3).

Хто бачить: лише група «Власник» (_check_screen першим рядком; адміністратор поза групою — відмова). Читання — правами користувача
(«Власник» читає місяці, рядки, поправки й звірку); sudo — лише назви планів статей власників і назва групи Energy. Відкрити записи — теж
правами самого користувача: модель без права читання — число без кліку; список — по фірмах периметра, до яких у користувача є доступ
(allowed_company_ids у контексті дії, круг 2б), а не лише по відмічених у перемикачі фірм — інакше список не зійдеться з числом.

Круг 2б: колонки таблиці, ряд графіка, «Разом» і «з початку року» плиток — один набір місяців (січень … обраний); неповний місяць —
позначка «неповний, по ДД.ММ» (calc.partial_day); «Разом» ступенів 1, 1а, 2 — записи ступеня за всі ці місяці (домени рядків деталі через
«АБО», calc.or_domains).

Круг 3 (слово власника 07.11 «экран: принимаю, только все должно быть кликабельно и также периоды должны быть»): усе на екрані — за обраним
періодом (calc.parse_period): плитки, водоспад, «Власники», «Перекази», «Окремо від прибутку», чипи — Σ місяців періоду (calc.period_sum);
таблиця й графік — місяці періоду (місяць — січень … він сам, як круг 2б). Клікабельно все: плитки (і «з початку року»), стовпці
водоспаду, рядки й підсумки карток, «частка» й «витрати компанії», чипи («не закрито» — місяці, звірка — звірки періоду, якість — три
кошики періоду, поправки — поправки періоду, «перераховано» — місяці); рядки кількох місяців — одним списком записів (calc.merge_items,
calc.merge_domain).

Круг 3б (ревю 3): «не оплачено» — залишок тих самих рахунків на сьогодні (_unpaid_now, лише читання, підпис «на сьогодні»; без права
читати рахунки — збережений на дату перерахунку, «на ДД.ММ»); клік стандартної моделі — свій список із колонкою «№» (CLICK_VIEWS);
«Прибутковість ліній →» — за обраним періодом.

Круг 3в (ревю 3б): «не оплачено» — залишок у валюті фірми (amount_residual_signed, EUR за курсом проводки), у списку рахунків кліку — та сама
колонка з сумою; свої види кліків — priority 1000; «Прибутковість ліній →» у році й періоді — підказка про межі М3."""
import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from . import calc

MONTH = 'workset.finance.month'
ITEM = 'workset.finance.item'
ADJUST = 'workset.finance.adjust'
CHECK = 'workset.finance.check'
TZ = 'Europe/Kyiv'   # «Перераховано ДД.ММ ГГ:ХХ» — за Києвом
ITEM_READ = ['month', 'kind', 'name', 'note', 'amount', 'res_model', 'domain', 'analytic_id', 'partner_id']
STEP_ITEMS = ('s1_docs', 's1a_owners_in_pl', 's2_ukraine')   # ступені, у яких є рядок деталі «Ступінь» (домен записів)
ADJ_STEP = {'s1g_no_analytic': 's1g', 's3_shares': 's3'}      # ступені, що складаються лише з поправок
PROFIT_MODEL = 'workset.profit.month'                        # «Прибутковість ліній» установлена — є посилання
PROFIT_GROUP = 'workset_profit.group_viewer'
PROFIT_TAG = 'workset_profit.overview'
CLICK_COS = 'workset_finance_click_cos'   # ключ контексту: фірми списку кліку (calc.click_companies), рахуються раз на виклик екрана
# круг 3б (правило власника 07.11 — «№» у кожному списку): клік, що відкриває стандартну модель, — свій список від штатного з колонкою «№»
# (views/workset_finance_screens_views.xml, priority 1000 — штатний вид моделі за замовчуванням не змінюється, навіть якщо в якогось штатного
# списку priority ≥ 100; круг 3в); моделі тут немає — штатний вид
CLICK_VIEWS = {
    'account.move.line': 'workset_finance.view_click_move_line_list',
    'account.analytic.line': 'workset_finance.view_click_analytic_line_list',
    'account.move': 'workset_finance.view_click_move_list',
}
INVOICE_CTX = {'default_move_type': 'out_invoice'}   # список рахунків клієнтів, як меню «Рахунки» Odoo: видно «Клієнт» і «Дата рахунку»


class WorksetFinanceScreens(models.Model):
    _inherit = MONTH

    # ——— службове ———
    def _open(self, title, model, domain=None, record=None, context=None):
        """Опис списку для кліку: модель, заголовок, домен, контекст без «Створити» (екран лише показує) і з allowed_company_ids — фірми
        периметра, доступні користувачу (CLICK_COS; інакше список бачив би лише фірми, відмічені в перемикачі); record — id одного запису
        (форма). Моделі немає або права читання в користувача немає — False (число без кліку). Стандартна модель (CLICK_VIEWS, круг 3б) —
        ще 'views': свій список із колонкою «№» і штатна форма."""
        if not model or model not in self.env or not self.env[model].has_access('read'):
            return False
        ctx = {'create': False}
        cos = self.env.context.get(CLICK_COS)
        if cos:
            ctx['allowed_company_ids'] = list(cos)
        out = {'model': model, 'title': title, 'domain': domain or [], 'context': dict(ctx, **(context or {}))}
        if record:
            out['res_id'] = record
        view = not record and model in CLICK_VIEWS and self.env.ref(CLICK_VIEWS[model], raise_if_not_found=False)
        if view:
            out['views'] = [[view.id, 'list'], [False, 'form']]
        return out

    def _unpaid_now(self, ids):
        """«Не оплачено» на сьогодні (круг 3б): рахунки, які перерахунок відніс до кошика (ids), — їхній залишок зараз за правилами
        перерахунку (calc.unpaid_now: amount_residual_signed — у валюті фірми, як _unpaid, круг 3в), правами користувача й по фірмах списку
        кліку (CLICK_COS) — число = списку кліку (колонка «Не оплачено, €» свого виду рахунків; рахунок, оплачений після перерахунку, зникає з
        обох). Лише читання. Рядки кошика не з рахунків (ids None) чи немає права читати рахунки — None: екран показує збережений залишок на
        дату перерахунку, як до круга 3б."""
        Move = self.env['account.move']
        if ids is None or not Move.has_access('read'):
            return None
        cos = self.env.context.get(CLICK_COS)
        if cos:
            Move = Move.with_context(allowed_company_ids=list(cos))
        return calc.unpaid_now(Move.search_read([('id', 'in', ids)], ['move_type', 'state', 'payment_state', 'amount_residual_signed']))

    def _click_companies(self):
        """Фірми списку кліку: периметр (як у перерахунку) ∩ фірми користувача, поточна — першою (calc.click_companies)."""
        return calc.click_companies(self._perimeter(), self.env.user.company_ids.ids, self.env.company.id)

    def _item_dom(self, item):
        """Домен рядка деталі (JSON, який записав перерахунок) → список; немає чи не JSON — None."""
        try:
            dom = json.loads(item.get('domain') or '[]') if item and item.get('res_model') else None
        except ValueError:
            return None
        return dom if isinstance(dom, list) else None

    def _item_open(self, item, title):
        """Рядок деталі → опис його записів (модель і домен, які записав перерахунок); домену немає чи він не JSON — False."""
        dom = self._item_dom(item)
        if dom is None:
            return False
        return self._open(title, item['res_model'], dom)

    def _group_open(self, group, title):
        """Група рядків деталі (calc.merge_items: рядки одного ключа за кілька місяців, круг 3) → опис її записів: один рядок — як рядок
        (_item_open); кілька — записи всіх одним списком (calc.merge_domain: id разом або «АБО» доменів, одна модель; сума списку = число);
        не склеюється — самі рядки деталі (у кожного кнопка «Записи»)."""
        if len(group['ids']) == 1:
            return self._item_open(group, title)
        dom = calc.merge_domain(group['domains']) if group.get('res_model') else None
        if dom:
            return self._open(title, group['res_model'], dom)
        return self._open(title, ITEM, [('id', 'in', group['ids'])])

    def _ids_open(self, ids, by_id, title):
        """Рядки деталі за id (by_id — прочитані рядки) → опис їхніх записів, як _group_open (рядок «Власників», «частка», «витрати компанії»)."""
        got = [by_id[i] for i in ids if i in by_id]
        if not got:
            return False
        return self._group_open(calc.merge_items(got, [])[0], title)

    def _energy_name(self):
        """Назва групи Energy для «Не оплачено …» — з Odoo під час роботи, не з коду (назва — у списку заборон публічного репозиторію):
        фірми, чий партнер у параметрі energy_partner_ids, а таких немає — самі партнери (комерційні); спільний початок назв —
        calc.common_name. Параметра немає — ''. sudo — лише назви."""
        ids = calc.param_value('ids', self.env['ir.config_parameter'].sudo().get_param(calc.P_PREFIX + 'energy_partner_ids') or '')
        if not ids:
            return ''
        names = self.env['res.company'].sudo().with_context(active_test=False).search([('partner_id', 'in', ids)], order='id').mapped('name')
        if not names:
            partners = self.env['res.partner'].sudo().with_context(active_test=False).browse(ids).exists()
            names = [p.commercial_partner_id.name or p.name for p in partners.sorted('id')]
        return calc.common_name(names)

    def _kyiv(self, dt, fmt):
        """Час (UTC з бази) → рядок за Києвом у форматі fmt; немає — ''."""
        if not dt:
            return ''
        return fields.Datetime.context_timestamp(self.with_context(tz=TZ), fields.Datetime.to_datetime(dt)).strftime(fmt)

    def _stamp(self, dt):
        """Коли перераховано → «07.11 06:30» за Києвом; немає — ''."""
        return self._kyiv(dt, '%d.%m %H:%M')

    def _step_open(self, key, months, rec_ids, steps, title):
        """Клік по числу ступеня key за місяці months (одна клітинка — один місяць, «Разом» — усі колонки: січень … обраний): 1, 1а, 2 —
        записи ступеня (домен рядка деталі «Ступінь»; за кілька місяців — домени місяців через «АБО», сума списку = «Разом», круг 2б; домену
        якогось місяця немає — самі рядки деталі, у кожного кнопка «Записи»); 1г і 3 — поправки; «до часток» і 4 — картка місяця (за кілька
        — список місяців); 4' — що віднімається (рядки «за грошима» й «не в за грошима» цих місяців, групами за видом, усередині — за лінією:
        одна лінія може дати два рядки деталі — рядки аналітики й рядки рахунку, круг 1е, — на екрані це одна група з одною сумою, не
        дробимо)."""
        one = len(months) == 1
        if key in STEP_ITEMS:
            got = [steps.get((m, key)) for m in months]
            if one:
                return self._item_open(got[0], title)
            doms = [self._item_dom(g) for g in got]
            same = all(d is not None for d in doms) and len({g['res_model'] for g in got}) == 1
            dom = calc.or_domains(doms) if same else None
            if dom:
                return self._open(title, got[0]['res_model'], dom)
            return self._open(title, ITEM, [('month', 'in', months), ('kind', '=', 'step'), ('note', '=', key)])
        if key in ADJ_STEP:
            return self._open(title, ADJUST, [('month', 'in', months), ('step', '=', ADJ_STEP[key])])
        if key == 's4c_cash':
            return self._open(title, ITEM, [('month', 'in', months), ('kind', 'in', ['cash', 'cash_other'])], context={'group_by': ['kind', 'line_id']})
        if one and rec_ids.get(months[0]):
            return self._open(title, MONTH, [('id', '=', rec_ids[months[0]])], record=rec_ids[months[0]])
        return self._open(title, MONTH, [('month', 'in', months)])

    def _owner_keys(self, items):
        """Стаття власника → [ключ, код]: стаття у своєму вузлі нижче вузла «власники» (параметр) — ключ і код — цей вузол (частка й витрати
        одного власника — один рядок); стаття прямо у вузлі «власники» — сама стаття, код — назва рядка деталі. sudo — лише назви планів."""
        root = calc.param_value('id', self.env['ir.config_parameter'].sudo().get_param(calc.P_PREFIX + 'owners_plan_id') or '')
        ids = sorted({it['analytic_id'][0] for it in items if it.get('analytic_id')})
        name = {it['analytic_id'][0]: it.get('name') or '—' for it in items if it.get('analytic_id')}
        out = {}
        for a in self.env['account.analytic.account'].sudo().with_context(active_test=False).browse(ids).exists():
            plan = a.plan_id
            out[a.id] = ['p%d' % plan.id, plan.name or '—'] if plan and root and plan.id != root else ['a%d' % a.id, name[a.id]]
        return out

    # ——— екран ———
    @api.model
    def finance_owner(self, period=None):
        """Екран «Власник» — один виклик (круг 3: за періодом). period — {'kind': 'month' | 'year' | 'range', 'from': 'РРРР-ММ', 'to':
        'РРРР-ММ'} (calc.parse_period), рядок місяця (старий виклик finance_owner(month) — місяць) або нічого — calc.default_month: останній
        закритий, а закритих немає — останній завершений календарний. Відмова (ValidationError): раніше за січень 2026, «від» пізніше за «до»,
        більше calc.MAX_MONTHS місяців, не розібрати. Віддає: вибір місяців і років (лише ті, по яких є запис), п'ять плиток (місяць — число й
        «з початку року»; рік і період — Σ місяців і «за N міс.»), чипи (лише коли є що сказати), водоспад ступенів (нульові сховано, сходиться
        до s4_net), ряд графіка (стовпці 4 і лінія «до часток»), «Власники» (за кодами власників: частка й витрати компанії), «Перекази на
        особисті рахунки», «Окремо від прибутку», таблиця «Драбина» (місяць — пораховані місяці від січня до обраного, «Разом» = «з початку
        року»; рік і період — пораховані місяці періоду, «Разом» = плиткам); у кожного числа — опис його записів ('open'). Лише читання. →
        {'period' (calc.period_info + 'anchor' — останній порахований місяць періоду: з нього перемикач іде в «Місяць» і «Рік»), 'month'
        (місяць — він сам, рік і період — останній місяць; і 'partial'), 'year', 'choices', 'years', 'max_months', 'has', 'state', 'threshold',
        'labels', 'tiles', 'chips', 'waterfall', 'series', 'owners', 'transfers', 'aside', 'ladder'}."""
        self._check_screen('owner')
        lang = self._lang()
        heads = [(calc.iso(r['month']), r['state']) for r in self.search_read([('month', '>=', calc.MIN_MONTH)], ['month', 'state'], order='month')]
        today = calc.iso(self._today())
        per = calc.parse_period(period, calc.default_month(heads, today))
        if per.get('refuse'):
            raise ValidationError(calc.t(per['refuse'], lang) % tuple(per['args']))
        one = per['kind'] == 'month'
        # якір: місяць — він сам; рік і період — останній місяць (рік таблиці місяця й «з початку року» — лише для місяця)
        first = per['to']
        # фірми списків кліку — раз на виклик (периметр ∩ фірми користувача), далі _open бере їх із контексту
        self = self.with_context(**{CLICK_COS: self._click_companies()})
        year = first[0:4]
        src_fields = [k + '_src' for k in calc.STEPS if k + '_src' in self._fields]
        # колонки, ряд графіка й «Разом»: місяць — січень … обраний (круг 2б: місяці після обраного не показуються); рік і період — місяці
        # періоду (круг 3)
        lo = max(year + '-01-01', calc.MIN_MONTH) if one else per['from']
        rows = self.search_read([('month', '>=', lo), ('month', '<=', per['to'])],
                                list(calc.MONEY) + src_fields + ['month', 'state', 'recomputed_at'], order='month')
        partial = {}
        for r in rows:
            r['month'] = calc.iso(r['month'])
            # неповний місяць: перераховано (день за Києвом) не пізніше його останнього дня — «неповний, по ДД.ММ»
            partial[r['month']] = calc.partial_day(r['month'], today, self._kyiv(r['recomputed_at'], '%Y-%m-%d'))
        in_p = set(per['months'])
        prow = [r for r in rows if r['month'] in in_p]   # місяці періоду з записом (місяць — він сам або нічого)
        pm = [r['month'] for r in prow]
        last = pm[-1] if pm else first
        part = partial.get(last, '') if prow else (calc.partial_day(first, today) if one else '')
        pinfo = dict(calc.period_info(per, lang, part), anchor=last[0:7])
        title_in = pinfo['title_in']
        months = [r['month'] for r in calc.period_rows(rows, per)]
        rec_ids = {r['month']: r['id'] for r in rows}
        state = (prow[0]['state'] if one else ('closed' if all(r['state'] == 'closed' for r in prow) else 'open')) if prow else ''
        out = {'period': pinfo, 'month': calc.month_info(first, lang, part if one else partial.get(first, '')), 'year': year,
               'choices': calc.month_choices(heads, lang), 'years': calc.year_choices(heads), 'max_months': calc.MAX_MONTHS, 'has': bool(prow),
               'state': state, 'threshold': calc.TRUTH_PCT, 'labels': {'open': calc.t('h_open', lang)}, 'tiles': [], 'chips': [], 'waterfall': False,
               'series': False, 'owners': False, 'transfers': False, 'aside': False, 'ladder': False}
        if not months:
            return out
        steps = {(calc.iso(i['month']), i['note']): i for i in self.env[ITEM].search_read(
            [('month', 'in', months), ('kind', '=', 'step')], ['month', 'note', 'res_model', 'domain'])}
        bases, all_bases = {}, {}
        for a in self.env[ADJUST].search_read([('month', 'in', months)], ['month', 'step', 'basis']):
            bases.setdefault(calc.iso(a['month']), {}).setdefault(a['step'], []).append(a['basis'] or '')
            all_bases.setdefault(a['step'], []).append(a['basis'] or '')
        of = calc.t('o_of', lang)
        # заголовок списку «Разом»: «січень – вересень 2026», «грудень 2026 – лютий 2027» (один місяць — він сам)
        span = calc.span_text(months[0], months[-1], lang)

        # таблиця «Драбина» і ряд графіка — ті самі колонки (місяць — січень … обраний; рік і період — місяці періоду)
        table = calc.ladder_table(rows, first, lang, partial, per)
        for r in table['rows']:
            label = '%s %s' % (r['num'], r['label'])
            for c in r['cells']:
                c['hint'] = calc.src_hint(r['key'], c['src'], bases.get(c['month']), lang)
                # нуль — «—» без кліку
                c['open'] = bool(calc.cents(c['value'])) and self._step_open(r['key'], [c['month']], rec_ids, steps,
                                                                             of % (label, calc.month_info(c['month'], lang)['title_in']))
            r['total']['hint'] = calc.src_hint(r['key'], r['total']['src'], all_bases, lang)
            r['total']['open'] = bool(calc.cents(r['total']['value'])) and self._step_open(r['key'], months, rec_ids, steps, of % (label, span))
        out['ladder'] = table
        out['series'] = calc.chart_series(table, lang)
        if not prow:
            return out
        # місяці періоду одним «місяцем» (Σ до цента; один місяць — він сам): водоспад, «Окремо від прибутку», «Власники», якість даних
        v = calc.period_sum(prow)

        # плитки: число — Σ місяців періоду (місяць — він сам) і свої записи; місяць — ще «з початку року» (січень … обраний, той самий
        # набір, що «Разом» таблиці) і його записи; рік і період — «за N міс.»
        def tile_opens(ms, span_in):
            return {
                's4_net': self._step_open('s4_net', ms, rec_ids, steps, of % (calc.t('r_s4_net', lang), span_in)),
                's4c_cash': self._step_open('s4c_cash', ms, rec_ids, steps, of % (calc.t('o_cash', lang), span_in)),
                'recruiting': self._open(of % (calc.t('o_recruiting', lang), span_in), ITEM, [
                    ('month', 'in', ms), '|', '&', ('kind', '=', 'step'), ('note', 'in', ['s1_docs', 's1a_owners_in_pl']),
                    '&', ('kind', '=', 'adjust'), ('note', '=', 's1g')]),
                's2_ukraine': self._step_open('s2_ukraine', ms, rec_ids, steps, of % (calc.t('w_s2_ukraine', lang), span_in)),
                's3_shares': self._step_open('s3_shares', ms, rec_ids, steps, of % (calc.t('w_s3_shares', lang), span_in)),
            }
        vo = tile_opens(pm, title_in)
        yo = tile_opens(months, span) if one else {}
        out['tiles'] = [dict(x, open=bool(calc.cents(x['value'])) and vo[x['key']], ytd_open=bool(one and calc.cents(x['ytd'])) and yo[x['key']],
                             note='' if one else calc.period_note(x['n'], lang)) for x in calc.period_tiles(rows, per)]

        # чипи — лише коли є що сказати: не закрито (місяць / скільки місяців), звірка (усі зійшлися / скільки ні), якість даних, поправки,
        # коли перераховано (найпізніше); кожен відкриває свої записи за період
        chips = []
        opened = [r['month'] for r in prow if r['state'] != 'closed']
        if opened:
            chips.append({'key': 'open', 'single': one, 'count': len(opened),
                          'open': self._open(of % (calc.t('o_months' if len(opened) == 1 else 'o_open_months', lang), title_in), MONTH,
                                             [('month', 'in', opened)], record=rec_ids[opened[0]] if len(opened) == 1 else None)})
        checks = self.env[CHECK].search_read([('month', 'in', pm)], ['month', 'ok', 'text'], order='month')
        if checks:
            bad = [c for c in checks if not c['ok']]
            chips.append({'key': 'check', 'single': one, 'ok': not bad, 'bad': len(bad), 'count': len(checks),
                          'text': (checks[0]['text'] or '') if one else '',
                          'open': self._open(of % (calc.t('o_check', lang), title_in), CHECK, [('month', 'in', pm)])})
        # частка за період — Σ кошиків / Σ обороту (calc.period_sum → quality_chip; один місяць — як було)
        q = calc.quality_chip(v, lang)
        if q:
            # клік — вікно «три кошики» з тієї самої відповіді (нового виклику немає): підписи — за кодом примітки рядка деталі мовою
            # користувача (calc.quality_baskets), не збережений текст мовою того, хто перераховував; кошик — свої записи всіх місяців
            # періоду одним списком (calc.merge_items за кодом). Поріг і «не розібрано X € із Y €» — у підказці чипа й у вікні
            qi = self.env[ITEM].search_read([('month', 'in', pm), ('kind', '=', 'quality')], ITEM_READ + ['count'], order='month, sort, id')
            groups = calc.merge_items(qi, ['note'])
            baskets = calc.quality_baskets(groups, lang)
            by_q = {g['id']: g for g in groups}
            for b in baskets:
                b['open'] = self._group_open(by_q[b['id']], of % (b['label'], title_in))
            chips.append(dict(q, key='quality', baskets=baskets, title=of % (calc.t('o_quality', lang), title_in),
                              open={'dialog': 'quality', 'hint': q['hint']} if baskets else False))
        n_adj = self.env[ADJUST].search_count([('month', 'in', pm)])
        if n_adj:
            chips.append({'key': 'adjust', 'count': n_adj, 'open': self._open(of % (calc.t('o_adjust', lang), title_in), ADJUST, [('month', 'in', pm)])})
        stamps = [r['recomputed_at'] for r in prow if r['recomputed_at']]
        if stamps:
            # клік — картка місяця (період — список місяців): коли перераховано кожен
            chips.append({'key': 'stamp', 'text': self._stamp(max(stamps)),
                          'open': self._open(of % (calc.t('o_months', lang), title_in), MONTH, [('month', 'in', pm)], record=rec_ids[pm[0]] if one else None)})
        out['chips'] = chips

        # водоспад за період: кожен стовпець — записи свого ступеня всіх місяців періоду (як «Разом» таблиці)
        fall = calc.fall_bars(v, lang)
        for b in fall['bars']:
            b['open'] = self._step_open(b['key'], pm, rec_ids, steps, of % (b['label'], title_in))
        out['waterfall'] = fall

        items = self.env[ITEM].search_read([('month', 'in', pm), ('kind', 'in', ['owner', 'owner_share', 'transfer', 'unpaid', 'stage2'])], ITEM_READ,
                                           order='month, sort, id')
        by_id = {it['id']: it for it in items}
        # «Власники»: рядок на код власника (стаття всіх місяців періоду — в одній групі), усередині — частка окремо від витрат компанії;
        # клік — рядки аналітики (рядок, «частка», «витрати компанії» — кожен свої)
        own = [it for it in items if it['kind'] in ('owner', 'owner_share')]
        groups = calc.owner_groups([dict(it, analytic=it['analytic_id'][0] if it['analytic_id'] else 0) for it in own], self._owner_keys(own))
        if groups:
            t_own = of % (calc.t('o_owners', lang), title_in)
            for g in groups:
                t_g = of % (g['code'], title_in)
                g['open'] = self._ids_open(g['ids'], by_id, t_g)
                g['share_open'] = bool(calc.cents(g['share'])) and self._ids_open(g['share_ids'], by_id, t_g)
                g['company_open'] = bool(calc.cents(g['company'])) and self._ids_open(g['company_ids'], by_id, t_g)
            out['owners'] = {'total': v['s5_owners'], 'share': v['s5_owners_share'], 'rows': groups,
                             'open': self._open(t_own, ITEM, [('month', 'in', pm), ('kind', 'in', ['owner', 'owner_share'])])}
        # «Перекази на особисті рахунки»: одержувач × сума × «розібрано» / «без документа» (за період — одержувач і статус одним рядком,
        # статус — за приміткою будь-якою мовою перерахунку); клік — рядки виписки
        tr_items = calc.merge_items([dict(it, status=calc.transfer_status(it['note'])) for it in items if it['kind'] == 'transfer'],
                                    ['partner_id', 'status'])
        tr = calc.transfer_rows(tr_items)
        if tr['rows']:
            by_tr = {g['id']: g for g in tr_items}
            for r in tr['rows']:
                r['open'] = self._group_open(by_tr[r['id']], of % (r['name'], title_in))
            t_tr = of % (calc.t('o_transfers', lang), title_in)
            tr['open'] = self._open(t_tr, ITEM, [('month', 'in', pm), ('kind', '=', 'transfer')])
            out['transfers'] = tr
        # «Окремо від прибутку»: II етап (клік — рядки аналітики чи рядки рахунку; обидва види разом — рядки деталі), не оплачено замовниками
        # й Energy (жовта крапка; назва групи — з Odoo, _energy_name; круг 3б: залишок тих самих рахунків на сьогодні — _unpaid_now, підпис
        # «на сьогодні»; без права читати рахунки — збережений на дату перерахунку свого місяця, «на ДД.ММ»); посилання — «Прибутковість
        # ліній» за тим самим періодом, якщо встановлена
        aside = []
        if calc.cents(v['s6_stage2']):
            t_s2 = of % (calc.t('o_stage2', lang), title_in)
            st2 = [it for it in items if it['kind'] == 'stage2']
            used = calc.merge_items([it for it in st2 if calc.cents(it['amount'])], ['res_model'])
            aside.append({'key': 'stage2', 'amount': v['s6_stage2'], 'asof': '',
                          'open': self._group_open(used[0], t_s2) if len(used) == 1 else self._open(t_s2, ITEM, [('id', 'in', [it['id'] for it in st2])])})
        for key, field, bucket in (('customers', 's7_unpaid_customers', 'customer'), ('energy', 's7_unpaid_energy', 'energy')):
            mine = [it for it in items if it['kind'] == 'unpaid' and it['note'] == bucket]
            if not mine and not calc.cents(v[field]):
                continue
            ids = calc.ids_union([it['domain'] for it in mine]) if all(it['res_model'] == 'account.move' for it in mine) else None
            firm = (self._energy_name() or 'Energy') if key == 'energy' else ''
            title = of % (calc.t('o_unpaid_energy', lang) % firm if key == 'energy' else calc.t('o_unpaid_customer', lang), title_in)
            now = self._unpaid_now(ids)
            if now is not None:
                # на сьогодні: число й список — ті самі рахунки, що досі не оплачені
                amount, asof = calc.eur(now['cents']), calc.t('p_today', lang)
                spec = now['ids'] and self._open(title, 'account.move', [('id', 'in', now['ids'])], context=INVOICE_CTX)
            else:
                amount = v[field]
                asof = calc.asof_text([self._kyiv(r['recomputed_at'], '%Y-%m-%d') for r in prow if calc.cents(r[field])], lang)
                spec = self._open(title, 'account.move', [('id', 'in', ids)], context=INVOICE_CTX) if ids else self._open(
                    title, ITEM, [('id', 'in', [it['id'] for it in mine])])
            if not calc.cents(amount):
                continue
            aside.append({'key': key, 'amount': amount, 'warn': key == 'energy', 'firm': firm, 'asof': asof, 'open': spec or False})
        profit = PROFIT_MODEL in self.env and self.env.user.has_group(PROFIT_GROUP)
        if aside:
            # круг 3б: «Прибутковість ліній →» — за обраним періодом (М3 з 19.0.5 приймає params.span {kind, from, to}: місяць, рік, «з–по»);
            # month — для старого М3 без span (останній місяць періоду)
            span = {'kind': per['kind'], 'from': per['from'], 'to': per['to']}
            out['aside'] = {'rows': aside, 'profit': {'tag': PROFIT_TAG, 'name': calc.t('o_profit', lang), 'month': last, 'span': span} if profit else False}
        return out
