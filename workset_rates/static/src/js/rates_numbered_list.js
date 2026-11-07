/** «№» першим стовпцем у списках «Ставок» (правило власника 07.11 для всіх екранів Odoo; номер — rates_row_numbers.listRowNumbers).
 *  Лише в наших видах і лише за прапорцем у розмітці виду:
 *  - список виду — корінь <list js_class="workset_rates_numbered"> (список ставок — свій js_class workset_rates_list, рендерер — нащадок
 *    цього); так і рядки карти проєктів (project.sale.line.employee.map, стандартна модель) — номер лише в нашому виді view_map_list, а не
 *    в усіх списках моделі;
 *  - вкладений список x2many у формі — widget="workset_rates_x2many" на полі (штатне поле x2many з цим рендерером).
 *  Штатні ListRenderer, X2ManyField і їхні шаблони не змінюються (patch немає; шаблони — копії primary): тести web / web_gantt (HOOT), які
 *  Odoo.sh гонить зі встановленим модулем, бачать ті самі класи й розмітку списків.
 *  Стовпець — службовий (type workset_rates_no) першим у columns рендерера: заголовок, рядок групи (назва групи займає й його), підвал,
 *  «Додати рядок», порожні рядки, ширини (useMagicColumnWidths: ширина 40px, не стискається й не розтягується) і переходи клавішами
 *  (комірка без o_data_cell — фокус її минає) беруть його з тих самих columns, тож стовпці не з'їжджають. У «Додаткових стовпцях» його
 *  немає (не з archInfo); у вивантаження не йде. Номери — раз на перемальовування (onWillRender): сортування, сторінка, згортання групи,
 *  видалення рядка дають нову нумерацію. */
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { onWillRender } from "@odoo/owl";
import { listRowNumbers } from "@workset_rates/js/rates_row_numbers";

export const ROW_NO_TYPE = "workset_rates_no";

export class NumberedListRenderer extends ListRenderer {
    static template = "workset_rates.NumberedListRenderer";
    static recordRowTemplate = "workset_rates.NumberedListRenderer.RecordRow";

    setup() {
        super.setup();
        this.rowNumbers = new Map();
        onWillRender(() => {
            this.rowNumbers = listRowNumbers(this.props.list);
        });
    }

    /** Стовпець «№» — перший серед стовпців (після прапорця вибору рядків, якщо він є). */
    getActiveColumns() {
        if (!this.rowNoColumn) {
            this.rowNoColumn = { id: ROW_NO_TYPE, type: ROW_NO_TYPE, name: ROW_NO_TYPE, label: "№", optional: false, attrs: { width: "40px" }, options: {} };
        }
        return [this.rowNoColumn, ...super.getActiveColumns()];
    }

    rowNumber(record) {
        return this.rowNumbers.get(record.id) || "";
    }
}

export class NumberedX2ManyField extends X2ManyField {
    static components = { ...X2ManyField.components, ListRenderer: NumberedListRenderer };
}

// поле — без displayName: службовий віджет модуля не з'являється у виборі віджетів (Studio тощо) поруч зі штатною «Relational table»
const { displayName: _stdName, ...x2ManyFieldBase } = x2ManyField;

registry.category("views").add("workset_rates_numbered", { ...listView, Renderer: NumberedListRenderer });
registry.category("fields").add("workset_rates_x2many", { ...x2ManyFieldBase, component: NumberedX2ManyField });
