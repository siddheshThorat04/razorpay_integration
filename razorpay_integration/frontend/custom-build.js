const fs = require('fs')
const path = require('path')

const OVERRIDES_DIR = path.resolve(__dirname, 'src_overrides')
const CRM_SRC = path.resolve(__dirname, '..', '..', '..', 'crm', 'frontend', 'src')

if (!fs.existsSync(CRM_SRC)) {
  console.warn(`crm_sms: CRM frontend not found at ${CRM_SRC} — skipping.`)
  process.exit(0)
}

function copyNewFile(relPath) {
  const src = path.join(OVERRIDES_DIR, relPath)
  const dest = path.join(CRM_SRC, relPath)
  fs.mkdirSync(path.dirname(dest), { recursive: true })
  fs.copyFileSync(src, dest)
  console.log(`crm_sms: copied ${relPath}`)
}

copyNewFile('components/Activities/SMSArea.vue')
copyNewFile('components/Activities/SMSBox.vue')
copyNewFile('components/Icons/SMSIcon.vue')
copyNewFile('composables/sms.js')

// --- Patch Activities.vue ---
{
  const filePath = path.join(CRM_SRC, 'components/Activities/Activities.vue')
  let content = fs.readFileSync(filePath, 'utf8')

  const importAnchor = `import { whatsappEnabled } from '@/composables/whatsapp'`
  if (content.includes(importAnchor) && !content.includes(`from '@/composables/sms'`)) {
    content = content.replace(
      importAnchor,
      importAnchor +
        `\nimport { smsEnabled } from '@/composables/sms'\nimport SMSArea from '@/components/Activities/SMSArea.vue'\nimport SMSBox from '@/components/Activities/SMSBox.vue'`
    )
  }

  const conditionAnchor = `        activities?.length ||\n        (whatsappMessages.data?.length && title == 'WhatsApp')\n      "`
  const conditionReplacement = `        activities?.length ||\n        (whatsappMessages.data?.length && title == 'WhatsApp') ||\n        (smsMessages.data?.length && title == 'SMS')\n      "`
  if (content.includes(conditionAnchor)) {
    content = content.replace(conditionAnchor, conditionReplacement)
  }

  const whatsappAreaBlock = `      <div v-if="title == 'WhatsApp' && whatsappMessages.data?.length">
        <WhatsAppArea
          v-model="whatsappMessages"
          v-model:reply="replyMessage"
          class="px-3 sm:px-10"
          :messages="whatsappMessages.data"
        />
      </div>`
  const smsAreaBlock = `\n      <div v-if="title == 'SMS' && smsMessages.data?.length">
        <SMSArea class="px-3 sm:px-10" :messages="smsMessages.data" />
      </div>`
  if (content.includes(whatsappAreaBlock) && !content.includes('SMSArea class')) {
    content = content.replace(whatsappAreaBlock, whatsappAreaBlock + smsAreaBlock)
  }

  const whatsappBoxBlock = `    <WhatsAppBox
      v-if="title == 'WhatsApp'"
      ref="whatsappBox"
      v-model="doc"
      v-model:reply="replyMessage"
      v-model:whatsapp="whatsappMessages"
      :doctype="doctype"
      @scroll="scroll"
    />`
  const smsBoxBlock = `\n    <SMSBox
      v-if="title == 'SMS'"
      ref="smsBox"
      v-model="doc"
      v-model:sms="smsMessages"
      :doctype="doctype"
      @scroll="scroll"
    />`
  if (content.includes(whatsappBoxBlock) && !content.includes('<SMSBox')) {
    content = content.replace(whatsappBoxBlock, whatsappBoxBlock + smsBoxBlock)
  }

  const resourceAnchor = `const whatsappMessages = createResource({
  url: 'crm.api.whatsapp.get_whatsapp_messages',
  cache: ['whatsapp_messages', props.docname],
  params: {
    reference_doctype: props.doctype,
    reference_name: props.docname,
  },
  auto: false,
  transform: (data) => sortByCreation(data),
  onSuccess: () => nextTick(() => scroll()),
})`
  const smsResource = `\n\nconst smsMessages = createResource({
  url: 'razorpay_integration.api.sms.get_sms_messages',
  cache: ['sms_messages', props.docname],
  params: {
    reference_doctype: props.doctype,
    reference_name: props.docname,
  },
  auto: false,
  transform: (data) => sortByCreation(data),
  onSuccess: () => nextTick(() => scroll()),
})

watch(
  smsEnabled,
  (enabled) => {
    if (enabled) smsMessages.fetch()
  },
  { immediate: true },
)`
  if (content.includes(resourceAnchor) && !content.includes('smsMessages = createResource')) {
    content = content.replace(resourceAnchor, resourceAnchor + smsResource)
  }

  fs.writeFileSync(filePath, content, 'utf8')
  console.log('crm_sms: Activities.vue patched')
}

// --- Patch Lead.vue ---
{
  const filePath = path.join(CRM_SRC, 'pages/Lead.vue')
  let content = fs.readFileSync(filePath, 'utf8')

  const tabAnchor = `    {
      name: 'WhatsApp',
      label: __('WhatsApp'),
      icon: WhatsAppIcon,
      condition: () => whatsappEnabled.value,
    },
  ]`
  const smsTab = `    {
      name: 'WhatsApp',
      label: __('WhatsApp'),
      icon: WhatsAppIcon,
      condition: () => whatsappEnabled.value,
    },
    {
      name: 'SMS',
      label: __('SMS'),
      icon: SMSIcon,
      condition: () => smsEnabled.value,
    },
  ]`
  if (content.includes(tabAnchor) && !content.includes(`name: 'SMS'`)) {
    content = content.replace(tabAnchor, smsTab)
  }

  const importAnchor = `const tabs = computed(() => {`
  const imports = `import SMSIcon from '@/components/Icons/SMSIcon.vue'\nimport { smsEnabled } from '@/composables/sms'\n\nconst tabs = computed(() => {`
  if (content.includes(importAnchor) && !content.includes(`from '@/composables/sms'`)) {
    content = content.replace(importAnchor, imports)
  }

  fs.writeFileSync(filePath, content, 'utf8')
  console.log('crm_sms: Lead.vue patched')
}


// --- Patch Deal.vue ---
{
  const filePath = path.join(CRM_SRC, 'pages/Deal.vue')
  let content = fs.readFileSync(filePath, 'utf8')

  const tabAnchor = `    {
      name: 'WhatsApp',
      label: __('WhatsApp'),
      icon: WhatsAppIcon,
      condition: () => whatsappEnabled.value,
    },
  ]`
  const smsTab = `    {
      name: 'WhatsApp',
      label: __('WhatsApp'),
      icon: WhatsAppIcon,
      condition: () => whatsappEnabled.value,
    },
    {
      name: 'SMS',
      label: __('SMS'),
      icon: SMSIcon,
      condition: () => smsEnabled.value,
    },
  ]`
  if (content.includes(tabAnchor) && !content.includes(`name: 'SMS'`)) {
    content = content.replace(tabAnchor, smsTab)
  }

  const importAnchor = `const tabs = computed(() => {`
  const imports = `import SMSIcon from '@/components/Icons/SMSIcon.vue'\nimport { smsEnabled } from '@/composables/sms'\n\nconst tabs = computed(() => {`
  if (content.includes(importAnchor) && !content.includes(`from '@/composables/sms'`)) {
    content = content.replace(importAnchor, imports)
  }

  fs.writeFileSync(filePath, content, 'utf8')
  console.log('crm_sms: Deal.vue patched')
}

console.log('crm_sms: all overrides applied successfully.')
