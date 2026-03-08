/**
 * Hyperliquid Wallet Section - Testnet/Mainnet wallet configuration
 *
 * Full wallet configuration UI extracted from WalletConfigPanel.
 * For use in ExchangeWalletsPanel accordion.
 */

import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Wallet, Eye, EyeOff, CheckCircle, RefreshCw, Trash2, Shield, ExternalLink, HelpCircle, X } from 'lucide-react'
import { createPortal } from 'react-dom'
import {
  getAccountWallet,
  configureAccountWallet,
  configureAgentWallet,
  testWalletConnection,
  deleteAccountWallet,
} from '@/lib/hyperliquidApi'
import { approveBuilder, type UnauthorizedAccount } from '@/lib/api'
import { copyToClipboard } from '@/lib/utils'
import { AuthorizationModal } from '@/components/hyperliquid'
import { useTranslation } from 'react-i18next'

interface HyperliquidWalletSectionProps {
  accountId: number
  accountName: string
  onStatusChange?: (env: 'testnet' | 'mainnet', configured: boolean) => void
  onWalletConfigured?: () => void
}

interface WalletData {
  id?: number
  walletAddress?: string
  maxLeverage: number
  defaultLeverage: number
  keyType?: 'private_key' | 'agent_key'
  masterWalletAddress?: string
  agentValidUntil?: string | null
  balance?: {
    totalEquity: number
    availableBalance: number
    marginUsagePercent: number
  }
}

type InputType = 'empty' | 'valid_key' | 'key_no_prefix' | 'wallet_address' | 'invalid'

function detectInputType(input: string): InputType {
  const trimmed = input.trim()
  if (!trimmed) return 'empty'
  const withoutPrefix = trimmed.startsWith('0x') ? trimmed.slice(2) : trimmed
  if (!/^[0-9a-fA-F]+$/.test(withoutPrefix)) return 'invalid'
  if (withoutPrefix.length === 64) {
    return trimmed.startsWith('0x') ? 'valid_key' : 'key_no_prefix'
  }
  if (withoutPrefix.length === 40) return 'wallet_address'
  return 'invalid'
}

function formatPrivateKey(input: string): string {
  const trimmed = input.trim()
  if (!trimmed) return ''
  const withoutPrefix = trimmed.startsWith('0x') ? trimmed.slice(2) : trimmed
  if (withoutPrefix.length === 64 && /^[0-9a-fA-F]+$/.test(withoutPrefix)) {
    return '0x' + withoutPrefix
  }
  return trimmed
}

export default function HyperliquidWalletSection({
  accountId,
  accountName,
  onStatusChange,
  onWalletConfigured
}: HyperliquidWalletSectionProps) {
  const { t } = useTranslation()
  const [testnetWallet, setTestnetWallet] = useState<WalletData | null>(null)
  const [mainnetWallet, setMainnetWallet] = useState<WalletData | null>(null)
  const [loading, setLoading] = useState(false)
  const [testingTestnet, setTestingTestnet] = useState(false)
  const [testingMainnet, setTestingMainnet] = useState(false)

  const [editingTestnet, setEditingTestnet] = useState(false)
  const [editingMainnet, setEditingMainnet] = useState(false)
  const [showTestnetKey, setShowTestnetKey] = useState(false)
  const [showMainnetKey, setShowMainnetKey] = useState(false)

  const [testnetPrivateKey, setTestnetPrivateKey] = useState('')
  const [testnetMaxLeverage, setTestnetMaxLeverage] = useState(3)
  const [testnetDefaultLeverage, setTestnetDefaultLeverage] = useState(1)
  const [testnetInputWarning, setTestnetInputWarning] = useState<string | null>(null)

  const [mainnetPrivateKey, setMainnetPrivateKey] = useState('')
  const [mainnetMaxLeverage, setMainnetMaxLeverage] = useState(3)
  const [mainnetDefaultLeverage, setMainnetDefaultLeverage] = useState(1)
  const [mainnetInputWarning, setMainnetInputWarning] = useState<string | null>(null)

  // Agent wallet binding
  const [testnetAgentKey, setTestnetAgentKey] = useState('')
  const [testnetMasterAddress, setTestnetMasterAddress] = useState('')
  const [mainnetAgentKey, setMainnetAgentKey] = useState('')
  const [mainnetMasterAddress, setMainnetMasterAddress] = useState('')

  const [tutorialOpen, setTutorialOpen] = useState(false)
  const [tutorialEnv, setTutorialEnv] = useState<'testnet' | 'mainnet'>('testnet')
  const [unauthorizedAccounts, setUnauthorizedAccounts] = useState<UnauthorizedAccount[]>([])
  const [authModalOpen, setAuthModalOpen] = useState(false)

  useEffect(() => {
    loadWalletInfo()
  }, [accountId])

  const loadWalletInfo = async () => {
    try {
      setLoading(true)
      const info = await getAccountWallet(accountId)

      const hasTestnet = !!info.testnetWallet
      const hasMainnet = !!info.mainnetWallet

      if (info.testnetWallet) {
        setTestnetWallet(info.testnetWallet)
        setTestnetMaxLeverage(info.testnetWallet.maxLeverage)
        setTestnetDefaultLeverage(info.testnetWallet.defaultLeverage)
      } else {
        setTestnetWallet(null)
      }

      if (info.mainnetWallet) {
        setMainnetWallet(info.mainnetWallet)
        setMainnetMaxLeverage(info.mainnetWallet.maxLeverage)
        setMainnetDefaultLeverage(info.mainnetWallet.defaultLeverage)
      } else {
        setMainnetWallet(null)
      }

      onStatusChange?.('testnet', hasTestnet)
      onStatusChange?.('mainnet', hasMainnet)
    } catch (error) {
      console.error('Failed to load wallet info:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSaveWallet = async (environment: 'testnet' | 'mainnet') => {
    const rawPrivateKey = environment === 'testnet' ? testnetPrivateKey : mainnetPrivateKey
    const maxLeverage = environment === 'testnet' ? testnetMaxLeverage : mainnetMaxLeverage
    const defaultLeverage = environment === 'testnet' ? testnetDefaultLeverage : mainnetDefaultLeverage

    if (!rawPrivateKey.trim()) {
      toast.error('Please enter a private key')
      return
    }

    const privateKey = formatPrivateKey(rawPrivateKey)
    const inputType = detectInputType(privateKey)

    if (inputType === 'wallet_address') {
      toast.error('You entered a wallet ADDRESS (40 chars), not a private key (64 chars).')
      return
    }
    if (inputType !== 'valid_key') {
      toast.error('Invalid private key format. Must be 64 hex characters.')
      return
    }

    try {
      setLoading(true)
      const result = await configureAccountWallet(accountId, {
        privateKey,
        maxLeverage,
        defaultLeverage,
        environment
      })

      if (result.success) {
        toast.success(`${environment} wallet configured: ${result.walletAddress.substring(0, 10)}...`)

        if (result.requires_authorization && result.walletAddress) {
          setUnauthorizedAccounts([{
            account_id: accountId,
            account_name: accountName,
            wallet_address: result.walletAddress,
            max_fee: 0,
            required_fee: 30
          }])
          setAuthModalOpen(true)
        }

        if (environment === 'testnet') {
          setTestnetPrivateKey('')
          setEditingTestnet(false)
        } else {
          setMainnetPrivateKey('')
          setEditingMainnet(false)
        }

        await loadWalletInfo()
        onWalletConfigured?.()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to configure wallet')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveAgentWallet = async (environment: 'testnet' | 'mainnet') => {
    const agentKey = environment === 'testnet' ? testnetAgentKey : mainnetAgentKey
    const masterAddr = environment === 'testnet' ? testnetMasterAddress : mainnetMasterAddress
    const maxLeverage = environment === 'testnet' ? testnetMaxLeverage : mainnetMaxLeverage
    const defaultLeverage = environment === 'testnet' ? testnetDefaultLeverage : mainnetDefaultLeverage

    if (!agentKey.trim() || !masterAddr.trim()) {
      toast.error(t('wallet.agent.bothFieldsRequired', 'Both Agent Private Key and Master Wallet Address are required'))
      return
    }

    const formattedKey = formatPrivateKey(agentKey)
    if (detectInputType(formattedKey) !== 'valid_key') {
      toast.error(t('wallet.agent.invalidAgentKey', 'Invalid agent private key format'))
      return
    }

    if (!/^0x[0-9a-fA-F]{40}$/i.test(masterAddr.trim())) {
      toast.error(t('wallet.agent.invalidMasterAddress', 'Invalid master wallet address format'))
      return
    }

    try {
      setLoading(true)
      const result = await configureAgentWallet(accountId, {
        agentPrivateKey: formattedKey,
        masterWalletAddress: masterAddr.trim(),
        environment,
        maxLeverage,
        defaultLeverage,
      })

      if (result.success) {
        toast.success(t('wallet.agent.configured', 'Agent wallet configured: {{addr}}', { addr: result.agentAddress.substring(0, 10) + '...' }))
        if (environment === 'testnet') {
          setTestnetAgentKey(''); setTestnetMasterAddress(''); setEditingTestnet(false)
        } else {
          setMainnetAgentKey(''); setMainnetMasterAddress(''); setEditingMainnet(false)
        }
        await loadWalletInfo()
        onWalletConfigured?.()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to configure agent wallet')
    } finally {
      setLoading(false)
    }
  }

  const handleTestConnection = async (environment: 'testnet' | 'mainnet') => {
    const setTesting = environment === 'testnet' ? setTestingTestnet : setTestingMainnet
    try {
      setTesting(true)
      const result = await testWalletConnection(accountId)
      if (result.success && result.connection === 'successful') {
        toast.success(`✅ Connection successful! Balance: $${result.accountState?.totalEquity.toFixed(2)}`)
        if (environment === 'mainnet' && result.walletAddress) {
          try {
            const authResult = await approveBuilder(accountId)
            if (!authResult.success || authResult.result?.status === 'err') {
              setUnauthorizedAccounts([{
                account_id: accountId,
                account_name: accountName,
                wallet_address: result.walletAddress,
                max_fee: 0,
                required_fee: 30
              }])
              setAuthModalOpen(true)
            }
          } catch (err) {
            console.error(`Builder binding failed:`, err)
          }
        }
      } else {
        toast.error(`❌ Connection failed: ${result.error || 'Unknown error'}`)
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Connection test failed')
    } finally {
      setTesting(false)
    }
  }

  const handleDeleteWallet = async (environment: 'testnet' | 'mainnet') => {
    if (!confirm(`Delete ${environment} wallet?`)) return
    try {
      setLoading(true)
      const result = await deleteAccountWallet(accountId, environment)
      if (result.success) {
        toast.success(`${environment} wallet deleted`)
        await loadWalletInfo()
        onWalletConfigured?.()
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete wallet')
    } finally {
      setLoading(false)
    }
  }

  const renderWalletBlock = (
    environment: 'testnet' | 'mainnet',
    wallet: WalletData | null,
    editing: boolean,
    setEditing: (v: boolean) => void,
    privateKey: string,
    setPrivateKey: (v: string) => void,
    maxLev: number,
    setMaxLev: (v: number) => void,
    defaultLev: number,
    setDefaultLev: (v: number) => void,
    showKey: boolean,
    setShowKey: (v: boolean) => void,
    testing: boolean,
    inputWarning: string | null,
    setInputWarning: (v: string | null) => void
  ) => {
    const envName = environment === 'testnet' ? 'Testnet' : 'Mainnet'
    const badgeVariant = environment === 'testnet' ? 'default' : 'destructive'

    return (
      <div className="p-4 border rounded-lg space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-muted-foreground" />
            <Badge variant={badgeVariant} className="text-xs">
              {environment === 'testnet' ? 'TESTNET' : 'MAINNET'}
            </Badge>
          </div>
          {wallet && !editing && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                {t('common.edit', 'Edit')}
              </Button>
              <Button variant="destructive" size="sm" onClick={() => handleDeleteWallet(environment)} disabled={loading}>
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          )}
        </div>

        {wallet && !editing ? (
          <div className="space-y-2">
            {wallet.keyType === 'agent_key' && (
              <div className="flex items-center gap-1.5 mb-1">
                <Shield className="h-3 w-3 text-green-500" />
                <span className="text-xs text-green-600 dark:text-green-400 font-medium">
                  {t('wallet.agent.secureMode', 'API Wallet (Secure)')}
                </span>
                {wallet.agentValidUntil && (
                  <span className="text-xs text-muted-foreground ml-auto">
                    {t('wallet.agent.expires', 'Expires')}: {new Date(wallet.agentValidUntil).toLocaleDateString()}
                  </span>
                )}
              </div>
            )}
            {wallet.keyType === 'agent_key' ? (
              <>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">
                    {t('wallet.agent.agentAddress', 'API Wallet Address')}
                    <span className="ml-1 text-green-600 dark:text-green-400">— {t('wallet.agent.agentAddressHint', 'Trading only, cannot withdraw')}</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 px-2 py-1 bg-muted rounded text-xs overflow-hidden">{wallet.walletAddress}</code>
                    <button onClick={async () => { const ok = await copyToClipboard(wallet.walletAddress || ''); if (ok) toast.success(t('wallet.addressCopied', 'Address copied')) }} className="cursor-pointer">
                      <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
                    </button>
                  </div>
                </div>
                {wallet.masterWalletAddress && (
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">
                      {t('wallet.agent.masterAddress', 'Master Wallet')}
                      <span className="ml-1">— {t('wallet.agent.masterAddressHint', 'Query balance & positions')}</span>
                    </label>
                    <code className="block px-2 py-1 bg-muted rounded text-xs overflow-hidden">{wallet.masterWalletAddress}</code>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t('wallet.walletAddress', 'Wallet Address')}</label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-2 py-1 bg-muted rounded text-xs overflow-hidden">{wallet.walletAddress}</code>
                  <button onClick={async () => { const ok = await copyToClipboard(wallet.walletAddress || ''); if (ok) toast.success(t('wallet.addressCopied', 'Address copied')) }} className="cursor-pointer">
                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
                  </button>
                </div>
              </div>
            )}

            {wallet.balance && (
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <div className="text-muted-foreground">{t('wallet.balance', 'Balance')}</div>
                  <div className="font-medium">${wallet.balance.totalEquity.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">{t('wallet.available', 'Available')}</div>
                  <div className="font-medium">${wallet.balance.availableBalance.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">{t('wallet.margin', 'Margin')}</div>
                  <div className="font-medium">{wallet.balance.marginUsagePercent.toFixed(1)}%</div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <div className="text-muted-foreground">{t('wallet.maxLeverage', 'Max Leverage')}</div>
                <div className="font-medium">{wallet.maxLeverage}x</div>
              </div>
              <div>
                <div className="text-muted-foreground">{t('wallet.defaultLeverage', 'Default Leverage')}</div>
                <div className="font-medium">{wallet.defaultLeverage}x</div>
              </div>
            </div>

            <Button variant="outline" size="sm" onClick={() => handleTestConnection(environment)} disabled={testing} className="w-full">
              {testing ? <><RefreshCw className="mr-2 h-3 w-3 animate-spin" />{t('wallet.testing', 'Testing...')}</> : t('wallet.testConnection', 'Test Connection')}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {!wallet && (
              <div className="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs">
                <p className="text-yellow-800">⚠️ {t('wallet.noWalletConfigured', 'No {{env}} wallet configured.', { env: envName.toLowerCase() })}</p>
              </div>
            )}

            {/* Tutorial button */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setTutorialEnv(environment); setTutorialOpen(true) }}
              className="w-full h-8 text-xs"
            >
              <HelpCircle className="mr-1 h-3 w-3" />
              {t('wallet.agent.viewTutorial', 'How to get an API Wallet (Step-by-step Guide)')}
            </Button>

            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t('wallet.agent.agentPrivateKey', 'API Wallet Private Key')}</label>
              <div className="flex gap-2">
                <Input
                  type={showKey ? 'text' : 'password'}
                  value={environment === 'testnet' ? testnetAgentKey : mainnetAgentKey}
                  onChange={(e) => environment === 'testnet' ? setTestnetAgentKey(e.target.value) : setMainnetAgentKey(e.target.value)}
                  placeholder="0x... (64 hex chars)"
                  className="font-mono text-xs h-8"
                />
                <Button type="button" variant="outline" size="sm" onClick={() => setShowKey(!showKey)} className="h-8 px-2">
                  {showKey ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                </Button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">{t('wallet.agent.masterWalletAddress', 'Master Wallet Address')}</label>
              <Input
                type="text"
                value={environment === 'testnet' ? testnetMasterAddress : mainnetMasterAddress}
                onChange={(e) => environment === 'testnet' ? setTestnetMasterAddress(e.target.value) : setMainnetMasterAddress(e.target.value)}
                placeholder="0x... (42 chars)"
                className="font-mono text-xs h-8"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t('wallet.maxLeverage', 'Max Leverage')}</label>
                <Input type="number" value={maxLev} onChange={(e) => setMaxLev(Number(e.target.value))} min={1} max={50} className="h-8 text-xs" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">{t('wallet.defaultLeverage', 'Default Leverage')}</label>
                <Input type="number" value={defaultLev} onChange={(e) => setDefaultLev(Number(e.target.value))} min={1} max={maxLev} className="h-8 text-xs" />
              </div>
            </div>

            <div className="flex gap-2">
              <Button onClick={() => handleSaveAgentWallet(environment)} disabled={loading} size="sm" className="flex-1 h-8 text-xs">
                {loading ? <><RefreshCw className="mr-2 h-3 w-3 animate-spin" />{t('wallet.saving', 'Saving...')}</> : <><Shield className="mr-1 h-3 w-3" />{t('wallet.agent.bindAgent', 'Bind API Wallet')}</>}
              </Button>
              {editing && (
                <Button variant="outline" onClick={() => { setEditing(false) }} size="sm" className="h-8 text-xs">
                  {t('common.cancel', 'Cancel')}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (loading && !testnetWallet && !mainnetWallet) {
    return (
      <div className="flex items-center justify-center py-4">
        <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        {renderWalletBlock(
          'testnet', testnetWallet, editingTestnet, setEditingTestnet,
          testnetPrivateKey, setTestnetPrivateKey,
          testnetMaxLeverage, setTestnetMaxLeverage,
          testnetDefaultLeverage, setTestnetDefaultLeverage,
          showTestnetKey, setShowTestnetKey, testingTestnet,
          testnetInputWarning, setTestnetInputWarning
        )}
        {renderWalletBlock(
          'mainnet', mainnetWallet, editingMainnet, setEditingMainnet,
          mainnetPrivateKey, setMainnetPrivateKey,
          mainnetMaxLeverage, setMainnetMaxLeverage,
          mainnetDefaultLeverage, setMainnetDefaultLeverage,
          showMainnetKey, setShowMainnetKey, testingMainnet,
          mainnetInputWarning, setMainnetInputWarning
        )}
      </div>

      <AuthorizationModal
        isOpen={authModalOpen}
        onClose={() => { setAuthModalOpen(false); setUnauthorizedAccounts([]) }}
        unauthorizedAccounts={unauthorizedAccounts}
        onAuthorizationComplete={() => { setAuthModalOpen(false); setUnauthorizedAccounts([]) }}
      />

      {/* API Wallet Tutorial Modal */}
      {tutorialOpen && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setTutorialOpen(false)} />
          <div className="relative bg-background border rounded-lg shadow-lg w-[830px] max-w-[95vw] mx-4 max-h-[85vh] overflow-hidden flex flex-col">
            <div className="p-4 border-b flex items-center justify-between">
              <h3 className="text-sm font-bold flex items-center gap-2">
                <Shield className="h-4 w-4 text-green-500" />
                {t('wallet.agent.tutorialTitle', 'How to Create an API Wallet')}
              </h3>
              <Button variant="ghost" size="sm" onClick={() => setTutorialOpen(false)} className="h-7 w-7 p-0">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="p-4 space-y-4 overflow-y-auto flex-1">
              {/* Step 1 */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">1</span>
                  <p className="text-sm font-medium">{t('wallet.agent.tutorialStep1', 'Open the API page, enter a name, and click "Authorize API Wallet"')}</p>
                </div>
                <a
                  href={tutorialEnv === 'testnet' ? 'https://app.hyperliquid-testnet.xyz/API' : 'https://app.hyperliquid.xyz/API'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium ml-7"
                >
                  {t('wallet.agent.openApiPage', 'Open Hyperliquid API Page')} <ExternalLink className="h-3 w-3" />
                </a>
                <img src="/static/step1.png" alt="Step 1" className="rounded border ml-7" style={{ maxWidth: '750px' }} />
              </div>
              {/* Step 2 */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">2</span>
                  <p className="text-sm font-medium">{t('wallet.agent.tutorialStep2', 'Copy the Private Key shown in the popup')}</p>
                </div>
                <div className="ml-7 p-2 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded text-xs text-red-700 dark:text-red-300">
                  ⚠️ {t('wallet.agent.tutorialStep2Warning', 'This key is only shown ONCE. If you close this popup without copying it, you will need to create a new API Wallet.')}
                </div>
                <img src="/static/step2.png" alt="Step 2" className="rounded border ml-7" style={{ maxWidth: '750px' }} />
              </div>
              {/* Step 3 */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-bold">3</span>
                  <p className="text-sm font-medium">{t('wallet.agent.tutorialStep3', 'Copy your Master Wallet Address from the top-right corner')}</p>
                </div>
                <img src="/static/step3.png" alt="Step 3" className="rounded border ml-7" style={{ maxWidth: '750px' }} />
              </div>
            </div>
            <div className="p-3 border-t">
              <Button onClick={() => setTutorialOpen(false)} size="sm" className="w-full text-xs">
                {t('wallet.agent.tutorialGotIt', 'Got it')}
              </Button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}
