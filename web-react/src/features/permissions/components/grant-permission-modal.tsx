import React, { useState, useMemo } from "react";
import { Button } from "../../../shared/components/button";
import { Modal } from "../../../shared/components/modal";
import { Input } from "../../../shared/components/input";
import { PermissionLevelSelect } from "../../../shared/components/permission-level-select";
import type {
  PermissionLevel,
  PermissionType,
} from "../../../shared/types/entity";

interface GrantPermissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (identifier: string, permission: PermissionLevel) => Promise<void>;
  title: string;
  label: string;
  options: (string | { label: string; value: string })[];
  type: PermissionType;
  isLoading?: boolean;
}

export const GrantPermissionModal: React.FC<GrantPermissionModalProps> = ({
  isOpen,
  onClose,
  onSave,
  title,
  label,
  options,
  type,
  isLoading = false,
}) => {
  const [selectedUsername, setSelectedUsername] = useState<string>("");
  const [selectedPermission, setSelectedPermission] =
    useState<PermissionLevel>("READ");
  const [searchTerm, setSearchTerm] = useState("");

  const normalizedOptions = useMemo(
    () =>
      options.map((opt) =>
        typeof opt === "string" ? { label: opt, value: opt } : opt,
      ),
    [options],
  );

  const filteredOptions = useMemo(
    () =>
      normalizedOptions.filter((opt) =>
        opt.label.toLowerCase().includes(searchTerm.toLowerCase()),
      ),
    [normalizedOptions, searchTerm],
  );

  const selectedLabel = normalizedOptions.find(
    (o) => o.value === selectedUsername,
  )?.label;

  const handleSave = async () => {
    if (!selectedUsername) return;
    await onSave(selectedUsername, selectedPermission);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title}>
      <div className="mb-4">
        <Input
          id="user-search"
          label={label}
          placeholder={`Search ${label.toLowerCase()}...`}
          value={searchTerm}
          onChange={(e) => {
            setSearchTerm(e.target.value);
            setSelectedUsername("");
          }}
          containerClassName="mb-2"
          autoComplete="off"
        />
        <div className="border border-ui-border dark:border-ui-border-dark rounded-md overflow-y-auto max-h-48">
          {filteredOptions.length === 0 ? (
            <p className="px-3 py-2 text-sm text-text-secondary dark:text-text-secondary-dark">
              No {label.toLowerCase()}s found
            </p>
          ) : (
            filteredOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`w-full text-left px-3 py-2 text-sm cursor-pointer transition-colors
                  ${
                    selectedUsername === opt.value
                      ? "bg-btn-primary text-white dark:bg-btn-primary-dark dark:text-white"
                      : "hover:bg-ui-secondary-bg dark:hover:bg-ui-secondary-bg-dark text-ui-text dark:text-ui-text-dark"
                  }`}
                onClick={() => setSelectedUsername(opt.value)}
              >
                {opt.label}
              </button>
            ))
          )}
        </div>
        {selectedLabel && (
          <p className="mt-1 text-sm text-text-secondary dark:text-text-secondary-dark">
            Selected: <span className="font-medium">{selectedLabel}</span>
          </p>
        )}
      </div>

      <PermissionLevelSelect
        id="permission-level"
        label="Permissions"
        value={selectedPermission}
        onChange={(val) => setSelectedPermission(val)}
        type={type}
        required
        containerClassName="mb-4"
      />

      <div className="flex justify-end space-x-3">
        <Button onClick={onClose} variant="ghost" disabled={isLoading}>
          Cancel
        </Button>
        <Button
          onClick={() => {
            void handleSave();
          }}
          variant="primary"
          disabled={isLoading || !selectedUsername}
        >
          {isLoading ? "Saving..." : "Save"}
        </Button>
      </div>
    </Modal>
  );
};