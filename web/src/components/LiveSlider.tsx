import { Slider } from "@heroui/react";
import { useState } from "react";

function sliderValue(value: number | number[]): number {
  return Array.isArray(value) ? (value[0] ?? 0) : value;
}

/** A slider that shows the dragged value at once and sends only when the drag ends. */
export function LiveSlider({
  label,
  value,
  min,
  max,
  step,
  onCommit,
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onCommit: (value: number) => void;
  format?: (value: number) => string;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const shown = dragging ?? value;
  return (
    <Slider
      aria-label={label}
      className="flex-1"
      minValue={min}
      maxValue={max}
      step={step}
      value={shown}
      onChange={(v) => setDragging(sliderValue(v))}
      onChangeEnd={(v) => {
        setDragging(null);
        onCommit(sliderValue(v));
      }}
      aria-valuetext={format ? format(shown) : undefined}
    >
      <Slider.Track>
        <Slider.Fill />
        <Slider.Thumb />
      </Slider.Track>
    </Slider>
  );
}
