export default function Settings() {
  return (
    <div className="space-y-7 p-8">
      <h1 className="text-[28px] font-semibold tracking-tight text-gray-900">Settings</h1>

      <div className="max-w-lg space-y-6">
        <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900">Email Account</h2>
          <div className="space-y-2">
            <p className="text-sm text-gray-500">
              Connect your email to send and receive through this app. Emails will come from your personal
              inbox — not from Jooba.
            </p>
            <button
              type="button"
              className="rounded-md bg-blue-500 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-600"
            >
              Connect Email Account
            </button>
          </div>
        </div>

        <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900">Follow-Up Reminders</h2>
          <p className="text-sm text-gray-500">
            Get reminded when a candidate hasn&apos;t responded after you reply.
          </p>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-900">Remind after:</span>
            <input
              type="number"
              defaultValue={5}
              className="h-9 w-16 rounded-md border border-gray-200 px-3 text-center text-sm"
            />
            <span className="text-sm text-gray-500">minutes</span>
          </div>
        </div>
      </div>
    </div>
  )
}
