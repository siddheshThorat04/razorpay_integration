<template>
  <div>
    <div
      v-for="sms in messages"
      :key="sms.name"
      class="activity group flex gap-2 mb-3"
      :class="sms.direction == 'Outgoing' ? 'flex-row-reverse' : ''"
    >
      <div
        class="max-w-[90%] rounded-md bg-surface-gray-1 text-ink-gray-9 p-2 text-base shadow-sm"
      >
        <Badge
          v-if="sms.status == 'Failed'"
          theme="red"
          :label="sms.status"
          class="mb-1"
        />
        <div class="whitespace-pre-wrap">{{ sms.message }}</div>
        <div class="mt-1 flex justify-end gap-1 text-ink-gray-5">
          <Tooltip :text="formatDate(sms.creation, 'ddd, MMM D, YYYY')">
            <div class="text-2xs">
              {{ formatDate(sms.creation, 'hh:mm a') }}
            </div>
          </Tooltip>
          <div v-if="sms.direction == 'Outgoing'" class="text-2xs">
            · {{ sms.status }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { formatDate } from '@/utils'
import { Tooltip, Badge } from 'frappe-ui'

defineProps({
  messages: { type: Array, default: () => [] },
})
</script>
