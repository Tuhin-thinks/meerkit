import { ref } from "vue";

const isBulkBatchRunning = ref(false);

export function setBulkBatchRunning(value: boolean): void {
    isBulkBatchRunning.value = value;
}

export function useUiTaskState() {
    return {
        isBulkBatchRunning,
    };
}
