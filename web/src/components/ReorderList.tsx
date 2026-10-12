import { useState, type ReactNode } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { restrictToVerticalAxis } from "@dnd-kit/modifiers";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

type ListProps = {
  ids: string[];
  labelOf: (id: string) => string;
  onReorder: (ids: string[]) => void;
  className?: string;
  children: ReactNode;
};

export function ReorderList({ ids, labelOf, onReorder, className, children }: ListProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function onDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    onReorder(arrayMove(ids, oldIndex, newIndex));
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[restrictToVerticalAxis]}
      onDragStart={(event) => setActiveId(String(event.active.id))}
      onDragCancel={() => setActiveId(null)}
      onDragEnd={onDragEnd}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ul className={className}>{children}</ul>
      </SortableContext>
      <DragOverlay>
        {activeId ? (
          <div className="flex items-center gap-2 rounded-xl border border-ink bg-elevated px-3 py-2.5 shadow-[0_16px_40px_rgba(18,20,15,0.18)]">
            <GripIcon />
            <span className="font-display text-sm font-bold">{labelOf(activeId)}</span>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

type ItemProps = {
  id: string;
  className?: string;
  children: ReactNode;
};

export function ReorderItem({ id, className, children }: ItemProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <li
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      className={`flex items-start gap-1.5 ${isDragging ? "relative z-10 opacity-35" : ""} ${className ?? ""}`}
    >
      <button
        type="button"
        aria-label="拖动调整顺序"
        className="mt-0.5 grid h-8 w-6 shrink-0 cursor-grab touch-none place-items-center rounded-md text-muted active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripIcon />
      </button>
      <div className="min-w-0 flex-1">{children}</div>
    </li>
  );
}

function GripIcon() {
  return (
    <svg width="14" height="18" viewBox="0 0 14 18" aria-hidden="true" className="fill-current">
      <circle cx="4" cy="3.5" r="1.25" />
      <circle cx="10" cy="3.5" r="1.25" />
      <circle cx="4" cy="9" r="1.25" />
      <circle cx="10" cy="9" r="1.25" />
      <circle cx="4" cy="14.5" r="1.25" />
      <circle cx="10" cy="14.5" r="1.25" />
    </svg>
  );
}
