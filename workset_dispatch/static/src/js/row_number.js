/** @odoo-module **/
// Колонка «№» у списку «Виїзди» (правило власника 07.11 ~14:4x: у кожній таблиці — номер рядка, щоб можна було сказати «питання по номеру 3»).
// Переносний віджет М3 (workset_profit/static/src/js/row_number.js, круг 5в) зі своїм ім'ям: модулі ставляться незалежно, тож кожен несе свій.
// Штатного номера рядка в списку Odoo немає — це поле-віджет: `<field name="id" widget="workset_dispatch_row_number" string="№" readonly="1"/>`
// (поле id є в будь-якої моделі, значення не використовується). Номер — місце запису в списку на екрані, а не id: після сортування й фільтра
// йде з 1, на другій сторінці — з (offset + 1), у згрупованому списку — всередині групи з 1.
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

export class DispatchRowNumberField extends Component {
    static template = "workset_dispatch.RowNumber";
    static props = { ...standardFieldProps };

    setup() {
        // ті самі записи в іншому порядку (сортування, сторінка) Owl сам не перемалює — перемальовуємо на «update» моделі
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

export const dispatchRowNumberField = {
    component: DispatchRowNumberField,
    displayName: _t("№"),
    supportedTypes: ["integer"],
};

registry.category("fields").add("workset_dispatch_row_number", dispatchRowNumberField);
