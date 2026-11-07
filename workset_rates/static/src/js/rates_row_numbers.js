/** «№» — порядковий номер рядка в таблицях «Ставок» (правило власника 07.11 для всіх екранів Odoo: «номер … понятно сколько действий и
 *  сколько задач требуется, также всегда можно сказать вопрос по номеру 3»). Номер — як рядок бачить людина на екрані: 1, 2, 3 …
 *  Чисті функції без Odoo — їх виконує node-тест (tools/tests/odoo_workset_rates_overview.test.js).
 *
 *  listRowNumbers(list) — список виду (і вкладений список x2many) → Map(id запису → номер):
 *  - без групування — зсув пейджера + місце на сторінці + 1 (list.offset);
 *  - з групуванням — наскрізно по записах у порядку показу: група за групою, вкладені групи — всередині своєї; згорнута група записів
 *    не показує — і номерів не бере; заголовки груп не нумеруються;
 *  - новий запис («Додати рядок», ще не збережений: isNew) — без номера й номера не займає. */
export function listRowNumbers(list) {
    const out = new Map();
    if (!list) {
        return out;
    }
    let n = list.isGrouped ? 0 : Number(list.offset) || 0;
    const take = (records) => {
        for (const record of records || []) {
            if (!record.isNew) {
                out.set(record.id, ++n);
            }
        }
    };
    const walk = (groups) => {
        for (const group of groups || []) {
            if (group.isFolded || !group.list) {
                continue;
            }
            if (group.list.isGrouped) {
                walk(group.list.groups);
            } else {
                take(group.list.records);
            }
        }
    };
    if (list.isGrouped) {
        walk(list.groups);
    } else {
        take(list.records);
    }
    return out;
}

/** «Огляд», «Тривоги»: номер рядка живої тривоги (людина чи ставка) — наскрізно по всіх рядках відкритих груп у порядку показу, щоб номер на
 *  панелі був один на рядок. Заголовки груп і тривог, розділи звірки («N пунктів») і рядок «Показано N з M» — без номера (це не записи,
 *  поруч із ними — лічильник). groups — alertGroups «Огляду», isOpen(group) — чи група розгорнута. → {ключ тривоги: номер її першого
 *  рядка − 1}: номер рядка = start + індекс рядка + 1. */
export function alertRowStarts(groups, isOpen) {
    const out = {};
    let n = 0;
    for (const group of groups || []) {
        if (isOpen && !isOpen(group)) {
            continue;
        }
        for (const alert of group.live || []) {
            out[alert.key] = n;
            n += (alert.rows || []).length;
        }
    }
    return out;
}
