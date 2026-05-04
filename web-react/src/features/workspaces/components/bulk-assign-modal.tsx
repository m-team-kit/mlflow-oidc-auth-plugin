import { useState } from "react";
import { Modal } from "../../../shared/components/modal";
import { Button } from "../../../shared/components/button";
import { PermissionLevelSelect } from "../../../shared/components/permission-level-select";
import { useToast } from "../../../shared/components/toast/use-toast";
import type { PermissionLevel } from "../../../shared/types/entity";

interface BulkAssignOption {
  label: string;
  value: string;
}

interface BulkAssignModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGrant: (name: string, permission: PermissionLevel) => Promise<boolean>;
  onSuccess: () => void;
  title: string;
  nameLabel: string;
  options: BulkAssignOption[];
}

interface BulkAssignResult {
  label: string;
  value: string;
  success: boolean;
}

export function BulkAssignModal({ isOpen, onClose, onGrant, onSuccess, title, nameLabel, options }: BulkAssignModalProps) {
  const { showToast } = useToast();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [permission, setPermission] = useState<PermissionLevel>("READ");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [results, setResults] = useState<BulkAssignResult[] | null>(null);
  const [filterText, setFilterText] = useState("");

  const filteredOptions = options.filter(
    (opt) => opt.label.toLowerCase().includes(filterText.toLowerCase()) || opt.value.toLowerCase().includes(filterText.toLowerCase()),
  );

  const handleToggle = (value: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      return next;
    });
    setResults(null);
  };

  const handleSelectAll = () => {
    setSelected((prev) => {
      const allFilteredSelected = filteredOptions.every((o) => prev.has(o.value));
      const next = new Set(prev);
      if (allFilteredSelected) {
        filteredOptions.forEach((o) => next.delete(o.value));
      } else {
        filteredOptions.forEach((o) => next.add(o.value));
      }
      return next;
    });
    setResults(null);
  };

  const handleSubmit = async () => {
    const selectedOptions = options.filter((o) => selected.has(o.value));
    if (selectedOptions.length === 0) {
      showToast("No items selected", "error");
      return;
    }

    setIsSubmitting(true);
    const collected: BulkAssignResult[] = [];

    for (const opt of selectedOptions) {
      const success = await onGrant(opt.value, permission);
      collected.push({ label: opt.label, value: opt.value, success });
    }

    setResults(collected);
    const successes = collected.filter((r) => r.success).length;
    const failures = collected.filter((r) => !r.success).length;

    if (failures === 0) {
      showToast(`Successfully assigned ${successes} permissions`, "success");
      onSuccess();
      handleClose();
    } else {
      showToast(`${successes} assigned, ${failures} failed`, "error");
      onSuccess();
    }

    setIsSubmitting(false);
  };

  const handleClose = () => {
    setSelected(new Set());
    setFilterText("");
    setResults(null);
    onClose();
  };

  const failedItems = results?.filter((r) => !r.success) ?? [];
  const successCount = results?.filter((r) => r.success).length ?? 0;
  const allFilteredSelected = filteredOptions.length > 0 && filteredOptions.every((o) => selected.has(o.value));

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={title} width="max-w-lg">
      <div key={isOpen ? "open" : "closed"}>
        <div className="mb-4">
          <label className="block text-sm font-medium text-text-primary dark:text-text-primary-dark mb-1">{nameLabel}*</label>

          {options.length === 0 ? (
            <p className="text-sm text-ui-text dark:text-ui-text-dark opacity-60 py-4">All {nameLabel.toLowerCase()} already have permissions for this workspace.</p>
          ) : (
            <>
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder={`Filter ${nameLabel.toLowerCase()}...`}
                className="w-full px-3 py-2 mb-2 border rounded-md focus:outline-none text-ui-text dark:text-ui-text-dark bg-ui-bg dark:bg-ui-bg-dark border-ui-border dark:border-ui-border-dark focus:border-btn-primary dark:focus:border-btn-primary-dark transition duration-150 ease-in-out"
              />

              <div className="flex items-center justify-between mb-1">
                <button
                  type="button"
                  onClick={handleSelectAll}
                  className="text-xs text-btn-primary dark:text-btn-primary-dark hover:underline"
                >
                  {allFilteredSelected ? "Deselect all" : "Select all"}
                </button>
                <span className="text-xs text-ui-text dark:text-ui-text-dark opacity-60">{selected.size} selected</span>
              </div>

              <div className="max-h-48 overflow-y-auto border rounded-md border-ui-border dark:border-ui-border-dark bg-ui-bg dark:bg-ui-bg-dark">
                {filteredOptions.length === 0 ? (
                  <p className="text-sm text-ui-text dark:text-ui-text-dark opacity-60 p-3">No matches found.</p>
                ) : (
                  filteredOptions.map((opt) => (
                    <label
                      key={opt.value}
                      className="flex items-center px-3 py-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(opt.value)}
                        onChange={() => handleToggle(opt.value)}
                        className="mr-2 rounded border-ui-border dark:border-ui-border-dark"
                      />
                      <span className="text-sm text-ui-text dark:text-ui-text-dark truncate">
                        {opt.label !== opt.value ? (
                          <>
                            {opt.label} <span className="opacity-60">({opt.value})</span>
                          </>
                        ) : (
                          opt.label
                        )}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </>
          )}
        </div>

        <PermissionLevelSelect id="bulk-permission-level" label="Permission" value={permission} onChange={(val) => setPermission(val)} required containerClassName="mb-4" />

        {results !== null && (
          <div className="mb-4 p-3 rounded-md bg-ui-bg dark:bg-ui-bg-dark border border-ui-border dark:border-ui-border-dark">
            {successCount > 0 && <p className="text-sm text-green-600 dark:text-green-400">{successCount} assigned successfully</p>}
            {failedItems.length > 0 && <p className="text-sm text-red-600 dark:text-red-400">{failedItems.length} failed: {failedItems.map((r) => r.label).join(", ")}</p>}
          </div>
        )}

        <div className="flex justify-end space-x-3">
          <Button onClick={handleClose} variant="ghost" disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} variant="primary" disabled={isSubmitting || selected.size === 0 || options.length === 0}>
            {isSubmitting ? "Assigning..." : `Assign ${selected.size > 0 ? selected.size : ""} Selected`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
