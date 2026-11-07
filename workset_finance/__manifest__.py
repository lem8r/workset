# -*- coding: utf-8 -*-
{
    'name': 'Фінанси',
    'summary': 'Екрани фінансів за ролями: «Власник» — драбина від доходу за документами до чистого прибутку, власники, II етап, неоплачено',
    'description': """
Хранимий підсумок «місяць драбини» (з січня 2026): рекрутинг за документами, власники в P&L, дохід без аналітики (поправки), Україна —
до часток; частки партнерів (поправки з підставою) — чистий прибуток; за грошима (перекази партнерам нетто); окремо власники, «II етап»,
неоплачено замовниками й Energy, посередництво, перекази на особисті рахунки, якість даних. Кожне число має пометку: факт / розрахунок /
поправка. Перерахунок — кнопкою, щоночі й інструментом штабу; звірка з аналітикою і проводками до цента. Параметри й склад груп пише
інструмент штабу через API — у модулі лише устрій.
""",
    'author': 'WorkSET',
    'website': 'https://workset.com.ua',
    'license': 'LGPL-3',
    'category': 'Accounting',
    # 19.0.1.1.0 (круг 2) — екран «Власник» (client action, ассети), меню «Власник» першим, переклад ru.po; 19.0.1.2.0 (круг 3) — період
    # екрана (місяць / рік / свій від місяця до місяця), клікабельно все, колонка «№» у списках карток; 19.0.1.3.0 (круг 3б) — колонка «№»
    # у списках Odoo (віджет row_number, свої primary-види рядків проводок, аналітики й рахунків для кліків), «не оплачено» — на сьогодні;
    # 19.0.1.3.1 (круг 3в) — «не оплачено» у валюті фірми (amount_residual_signed) і така сама колонка з сумою в списку рахунків кліку,
    # priority своїх видів 1000, підписи «на день перерахунку» й підказка «Прибутковість ліній →»; моделі й поля ті самі — після -u
    # перерахунок потрібен лише місяцям із рахунками не в євро (збережене «не оплачено» в них — у валюті документа)
    'version': '19.0.1.3.1',
    # workset_rates — периметр фірм (_skip_companies) і лінії (workset.line); account, analytic — проводки й аналітика; hr — розділ кадрів
    # форми користувача для привілею; mail — листування поправок; web (Chart.js екрана) — через account
    'depends': ['workset_rates', 'account', 'hr', 'analytic', 'mail'],
    'data': [
        'security/workset_finance_security.xml',
        'security/ir.model.access.csv',
        'views/workset_finance_month_views.xml',
        'views/workset_finance_item_views.xml',
        'views/workset_finance_adjust_views.xml',
        'views/workset_finance_check_views.xml',
        'views/workset_finance_screens_views.xml',
        'views/menus.xml',
        'data/ir_cron.xml',
    ],
    # круг 2: екран «Власник» (client action OWL)
    'assets': {
        'web.assets_backend': [
            'workset_finance/static/src/scss/workset_finance.scss',
            'workset_finance/static/src/js/finance_screens.js',
            'workset_finance/static/src/xml/finance_screens.xml',
            # круг 3б: колонка «№» списків Odoo (перенесено з М3 під своїм іменем: цей JS + шаблон)
            'workset_finance/static/src/js/row_number.js',
            'workset_finance/static/src/xml/row_number.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}
