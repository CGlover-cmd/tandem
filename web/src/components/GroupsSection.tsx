import { Button, Input, Label, Spinner, Switch, TextField } from "@heroui/react";
import { useState } from "react";

import { outputLive } from "../audio";
import { strings } from "../strings";
import type { AudioOutput, Command, SpeakerGroup } from "../types";

/** Saved speaker groups, each with one switch, and "save the playing speakers as a group". */
export function GroupsSection({
  groups,
  outputs,
  send,
}: {
  groups: SpeakerGroup[];
  outputs: AudioOutput[];
  send: (command: Command) => void;
}) {
  const words = strings.groups;
  const playing = outputs.filter((o) => outputLive(o) && o.state !== "direct");
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const names = new Map(outputs.map((o) => [o.id, o.name]));

  const save = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    send({ type: "saveGroup", name: trimmed, outputs: playing.map((o) => o.id) });
    setName("");
    setNaming(false);
  };

  if (groups.length === 0 && playing.length < 2) return null;
  return (
    <section className="flex flex-col gap-2" aria-labelledby="groups-label">
      <h3 id="groups-label" className="section-title">
        {words.title}
      </h3>
      {groups.length > 0 && (
        <ul className="flex flex-col gap-2" aria-labelledby="groups-label">
          {groups.map((group) => {
            const members = group.outputs.map((id) => names.get(id)).filter(Boolean).join(", ");
            const on = group.state === "on" || group.state === "partly";
            return (
              <li key={group.id} className="output-row glass flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-semibold">{group.name}</p>
                  <p className="truncate text-[12px] text-[var(--muted)]">
                    {group.state === "partly" ? words.partly(members) : members || words.noneAround}
                  </p>
                </div>
                {group.state === "starting" && <Spinner size="sm" color="accent" aria-hidden="true" />}
                <Button
                  size="sm"
                  variant="tertiary"
                  aria-label={words.delete(group.name)}
                  onPress={() => send({ type: "deleteGroup", id: group.id })}
                >
                  {words.remove}
                </Button>
                <Switch
                  isSelected={on}
                  isDisabled={group.state === "starting"}
                  onChange={(turnOn) => send({ type: "setGroup", id: group.id, on: turnOn })}
                >
                  <Switch.Content>
                    <Switch.Control>
                      <Switch.Thumb />
                    </Switch.Control>
                    <span className="sr-only">{words.turnOn(group.name)}</span>
                  </Switch.Content>
                </Switch>
              </li>
            );
          })}
        </ul>
      )}
      {playing.length >= 2 &&
        (naming ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              save();
            }}
          >
            <TextField value={name} onChange={setName} maxLength={40} autoFocus className="flex-1">
              <Label className="sr-only">{words.nameLabel}</Label>
              <Input placeholder={words.namePlaceholder} autoComplete="off" />
            </TextField>
            <Button size="sm" variant="primary" type="submit" isDisabled={!name.trim()}>
              {words.save}
            </Button>
            <Button size="sm" variant="secondary" onPress={() => setNaming(false)}>
              {words.cancel}
            </Button>
          </form>
        ) : (
          <Button size="sm" variant="secondary" className="self-start" onPress={() => setNaming(true)}>
            {words.saveAs(playing.length)}
          </Button>
        ))}
    </section>
  );
}
