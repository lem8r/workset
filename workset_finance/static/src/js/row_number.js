/** @odoo-module **/
// Колонка «№» у списках Odoo 19 («Фінанси», круг 3б; правило власника 07.11: «номер: оставить … всегда можно сказать вопрос по номеру 3»).
// Штатного номера рядка в списку немає — це поле-віджет: у виді списку стоїть `<field name="id" widget="workset_finance_row_number" string="№"
// readonly="1" width="50px"/>` (поле id є в будь-якої моделі, його значення не показується). Номер — місце запису в списку на екрані, а не id:
// після сортування й фільтра йде з 1, на другій сторінці пейджера — з (offset + 1), у згрупованому списку — усередині групи з 1.
// Перенесено з «Прибутковості» (М3, віджет workset_profit_row_number) під своїм іменем — без залежності від workset_profit.
// Для рядків усередині форми (one2many) не годиться: там у запису немає «свого» списку — числа немає.
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** Номер запису в списку: зсув сторінки + місце на сторінці + 1; немає в списку — 0. Групи — рекурсивно, номери з 1 у кожній. */
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
    static template = "workset_finance.RowNumber";
    static props = { ...standardFieldProps };

    setup() {
        // рядки з тими самими записами в іншому порядку (сортування, сторінка) Owl сам не перемалює — перемальовуємо на «update» моделі
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

registry.category("fields").add("workset_finance_row_number", rowNumberField);
