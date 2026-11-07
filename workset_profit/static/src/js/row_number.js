/** @odoo-module **/
// Колонка «№» в списках Odoo 19 (М3, круг 5в; правило владельца 07.11: у каждой таблицы — номер строки, чтобы можно было сказать «вопрос по
// номеру 3»). Штатного номера строки в списке нет — это поле-виджет: в виде списка ставится `<field name="id" widget="workset_profit_row_number"
// string="№" readonly="1" width="50px"/>` (поле id есть у любой модели, значение не используется). Номер — место записи в списке на экране,
// а не id: после сортировки и фильтра идёт с 1, на второй странице пейджера — с (offset + 1), в сгруппированном списке — внутри группы с 1.
// Переносимо: файл JS + шаблон row_number.xml и две строки в assets модуля — больше ничего (модуль-сосед берёт оба файла как есть).
// Не подходит для строк внутри формы (one2many): там у записи нет «своего» списка — число не показываем.
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** Номер записи в списке: смещение страницы + место на странице + 1; нет в списке — 0. Группы — рекурсивно, номера с 1 в каждой. */
export function rowNumber(list, record) {
    if (!list || !record) {
        return 0;
    }
    if (list.isGrouped || Array.isArray(list.groups)) {
        for (const group of list.groups || []) {
            const n = rowNumber(group.list, record);
            if (n) {
                return n;
            }
        }
        return 0;
    }
    const at = (list.records || []).indexOf(record);
    return at < 0 ? 0 : (list.offset || 0) + at + 1;
}

export class RowNumberField extends Component {
    static template = "workset_profit.RowNumber";
    static props = { ...standardFieldProps };

    setup() {
        // строки с теми же записями, но в другом порядке (сортировка, страница) Owl сам не перерисует — перерисовываем на «update» модели
        this.tick = useState({ n: 0 });
        const model = this.props.record && this.props.record.model;
        if (model && model.bus) {
            useBus(model.bus, "update", () => this.tick.n++);
        }
    }

    get number() {
        this.tick.n;
        const model = this.props.record && this.props.record.model;
        return rowNumber(model && model.root, this.props.record) || "";
    }
}

export const rowNumberField = {
    component: RowNumberField,
    displayName: _t("№"),
    supportedTypes: ["integer"],
};

registry.category("fields").add("workset_profit_row_number", rowNumberField);
