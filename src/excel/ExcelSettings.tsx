import type { ExcelOptions, Sheet } from "./workbook";
export function ExcelSettings({
  sheets,
  value,
  change,
  disabled,
}: {
  sheets: Sheet[];
  value: ExcelOptions;
  change: (value: ExcelOptions) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="excel-settings" disabled={disabled}>
      <legend>Worksheets and page layout</legend>
      {sheets.filter((sheet) => !sheet.hidden).length > 1 && (
        <div className="word-actions">
          <button
            className="secondary"
            type="button"
            onClick={() =>
              change({
                ...value,
                sheets: sheets
                  .filter((sheet) => !sheet.hidden)
                  .map((sheet) => sheet.index),
              })
            }
          >
            Select all visible
          </button>
          <button
            className="secondary"
            type="button"
            disabled={!value.sheets.length}
            onClick={() => change({ ...value, sheets: [] })}
          >
            Clear selection
          </button>
        </div>
      )}
      <div className="excel-sheets">
        {sheets
          .filter((sheet) => !sheet.hidden)
          .map((sheet) => (
            <label key={sheet.index}>
              <input
                type="checkbox"
                aria-label={sheet.name}
                checked={value.sheets.includes(sheet.index)}
                onChange={(event) =>
                  change({
                    ...value,
                    sheets: event.target.checked
                      ? [...value.sheets, sheet.index].sort((a, b) => a - b)
                      : value.sheets.filter((i) => i !== sheet.index),
                  })
                }
              />
              <span>
                {sheet.name}
                {sheet.active ? " (current worksheet)" : ""}
              </span>
            </label>
          ))}
      </div>
      {!!sheets.filter((sheet) => sheet.hidden).length && (
        <p>
          {sheets.filter((sheet) => sheet.hidden).length} hidden worksheet(s)
          excluded.
        </p>
      )}
      {!value.sheets.length && (
        <p role="status">Select at least one visible worksheet.</p>
      )}
      <label>
        Scaling
        <select
          aria-label="Scaling"
          value={value.scale}
          onChange={(event) =>
            change({
              ...value,
              scale: event.target.value as ExcelOptions["scale"],
            })
          }
        >
          <option value="keep">Keep original print settings</option>
          <option value="auto">Automatic (recommended)</option>
          <option value="width">Fit all columns to page width</option>
          <option value="page">Fit whole sheet on one page</option>
        </select>
      </label>
      <label>
        Orientation
        <select
          aria-label="Orientation"
          value={value.orientation}
          onChange={(e) =>
            change({
              ...value,
              orientation: e.target.value as ExcelOptions["orientation"],
            })
          }
        >
          <option value="keep">Automatic / saved setting</option>
          <option value="portrait">Portrait</option>
          <option value="landscape">Landscape</option>
        </select>
      </label>
      <details>
        <summary>More page settings</summary>
        <label>
          Paper size
          <select
            aria-label="Paper size"
            value={value.paper}
            onChange={(e) =>
              change({
                ...value,
                paper: e.target.value as ExcelOptions["paper"],
              })
            }
          >
            <option value="keep">Keep each sheet's setting</option>
            <option value="A4">A4</option>
            <option value="Letter">Letter</option>
          </select>
        </label>
      </details>
    </fieldset>
  );
}
