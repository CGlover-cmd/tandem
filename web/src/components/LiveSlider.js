import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Slider } from "@heroui/react";
import { useState } from "react";
function sliderValue(value) {
    return Array.isArray(value) ? (value[0] ?? 0) : value;
}
/** A slider that shows the dragged value at once and sends only when the drag ends. */
export function LiveSlider({ label, value, min, max, step, onCommit, format, }) {
    const [dragging, setDragging] = useState(null);
    const shown = dragging ?? value;
    return (_jsx(Slider, { "aria-label": label, className: "flex-1", minValue: min, maxValue: max, step: step, value: shown, onChange: (v) => setDragging(sliderValue(v)), onChangeEnd: (v) => {
            setDragging(null);
            onCommit(sliderValue(v));
        }, "aria-valuetext": format ? format(shown) : undefined, children: _jsxs(Slider.Track, { children: [_jsx(Slider.Fill, {}), _jsx(Slider.Thumb, {})] }) }));
}
