import os
import shutil

import frappe


def after_install():
	bench_path = frappe.utils.get_bench_path()
	crm_src = os.path.join(bench_path, "apps", "crm", "frontend", "src")
	overrides_dir = os.path.join(
		bench_path, "apps", "razorpay_integration", "razorpay_integration",
		"frontend_overrides"
	)

	if not os.path.isdir(crm_src):
		print("razorpay_integration: CRM frontend not found, skipping SMS tab patch.")
		return

	new_files = [
		"components/Activities/SMSArea.vue",
		"components/Activities/SMSBox.vue",
		"components/Icons/SMSIcon.vue",
		"composables/sms.js",
	]
	for rel_path in new_files:
		src = os.path.join(overrides_dir, rel_path)
		dest = os.path.join(crm_src, rel_path)
		os.makedirs(os.path.dirname(dest), exist_ok=True)
		shutil.copyfile(src, dest)
		print(f"razorpay_integration: copied {rel_path}")

	_patch_activities(crm_src)
	_patch_tabs_file(os.path.join(crm_src, "pages", "Lead.vue"))
	_patch_tabs_file(os.path.join(crm_src, "pages", "Deal.vue"))

	print("razorpay_integration: SMS tab patch applied. Run `bench build --app crm` to rebuild.")


def _patch_activities(crm_src):
	file_path = os.path.join(crm_src, "components", "Activities", "Activities.vue")
	with open(file_path) as f:
		content = f.read()

	import_anchor = "import { whatsappEnabled } from '@/composables/whatsapp'"
	if import_anchor in content and "@/composables/sms'" not in content:
		content = content.replace(
			import_anchor,
			import_anchor
			+ "\nimport { smsEnabled } from '@/composables/sms'"
			+ "\nimport SMSArea from '@/components/Activities/SMSArea.vue'"
			+ "\nimport SMSBox from '@/components/Activities/SMSBox.vue'",
		)

	condition_anchor = """        activities?.length ||
        (whatsappMessages.data?.length && title == 'WhatsApp')
      \""""
	condition_replacement = """        activities?.length ||
        (whatsappMessages.data?.length && title == 'WhatsApp') ||
        (smsMessages.data?.length && title == 'SMS')
      \""""
	if condition_anchor in content:
		content = content.replace(condition_anchor, condition_replacement)

	whatsapp_area_block = """      <div v-if="title == 'WhatsApp' && whatsappMessages.data?.length">
        <WhatsAppArea
          v-model="whatsappMessages"
          v-model:reply="replyMessage"
          class="px-3 sm:px-10"
          :messages="whatsappMessages.data"
        />
      </div>"""
	sms_area_block = """
      <div v-if="title == 'SMS' && smsMessages.data?.length">
        <SMSArea class="px-3 sm:px-10" :messages="smsMessages.data" />
      </div>"""
	if whatsapp_area_block in content and "SMSArea class" not in content:
		content = content.replace(whatsapp_area_block, whatsapp_area_block + sms_area_block)

	whatsapp_box_block = """    <WhatsAppBox
      v-if="title == 'WhatsApp'"
      ref="whatsappBox"
      v-model="doc"
      v-model:reply="replyMessage"
      v-model:whatsapp="whatsappMessages"
      :doctype="doctype"
      @scroll="scroll"
    />"""
	sms_box_block = """
    <SMSBox
      v-if="title == 'SMS'"
      ref="smsBox"
      v-model="doc"
      v-model:sms="smsMessages"
      :doctype="doctype"
      @scroll="scroll"
    />"""
	if whatsapp_box_block in content and "<SMSBox" not in content:
		content = content.replace(whatsapp_box_block, whatsapp_box_block + sms_box_block)

	resource_anchor = """const whatsappMessages = createResource({
  url: 'crm.api.whatsapp.get_whatsapp_messages',
  cache: ['whatsapp_messages', props.docname],
  params: {
    reference_doctype: props.doctype,
    reference_name: props.docname,
  },
  auto: false,
  transform: (data) => sortByCreation(data),
  onSuccess: () => nextTick(() => scroll()),
})"""
	sms_resource = """

const smsMessages = createResource({
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
)"""
	if resource_anchor in content and "smsMessages = createResource" not in content:
		content = content.replace(resource_anchor, resource_anchor + sms_resource)

	with open(file_path, "w") as f:
		f.write(content)
	print("razorpay_integration: patched Activities.vue")


def _patch_tabs_file(file_path):
	with open(file_path) as f:
		content = f.read()

	tab_anchor = """    {
      name: 'WhatsApp',
      label: __('WhatsApp'),
      icon: WhatsAppIcon,
      condition: () => whatsappEnabled.value,
    },
  ]"""
	sms_tab = """    {
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
  ]"""
	if tab_anchor in content and "name: 'SMS'" not in content:
		content = content.replace(tab_anchor, sms_tab)

	import_anchor = "const tabs = computed(() => {"
	imports = (
		"import SMSIcon from '@/components/Icons/SMSIcon.vue'\n"
		"import { smsEnabled } from '@/composables/sms'\n\n"
		"const tabs = computed(() => {"
	)
	if import_anchor in content and "@/composables/sms'" not in content:
		content = content.replace(import_anchor, imports)

	with open(file_path, "w") as f:
		f.write(content)
	print(f"razorpay_integration: patched {os.path.basename(file_path)}")
