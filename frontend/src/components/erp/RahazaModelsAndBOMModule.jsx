/**
 * RahazaModelsAndBOMModule — Combined Module (Task 1.3 + Phase 5b)
 * Menggabungkan Master Model + BOM + Size Matrix dalam satu tampilan bertab.
 * Phase 5b: Upgrade BOM dengan multi-version support.
 */
import { useState, useEffect } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Shirt, ListTree, Ruler, Boxes, Palette, Tags } from 'lucide-react';
import RahazaModelsModule from './RahazaModelsModule';
import RahazaBOMModuleV2 from './RahazaBOMModuleV2';
import RahazaSizesModule from './RahazaSizesModule';
import RahazaVariantsModule from './RahazaVariantsModule';
import RahazaColorsModule from './RahazaColorsModule';
import RahazaProductCategoriesModule from './RahazaProductCategoriesModule';

export default function RahazaModelsAndBOMModule({ token, user, headers, userRole, hasPerm, onNavigate, moduleId }) {
  // Allow deep linking via sessionStorage (set by redirect from prod-models, prod-bom, prod-sizes)
  const getInitialTab = () => {
    const stored = sessionStorage.getItem('models_bom_tab');
    if (stored && ['models', 'categories', 'variants', 'bom', 'sizes', 'colors'].includes(stored)) {
      sessionStorage.removeItem('models_bom_tab');
      return stored;
    }
    return 'models';
  };

  const [activeTab, setActiveTab] = useState(getInitialTab);

  return (
    <div className="space-y-4" data-testid="models-bom-module">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">DA Product Master</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Kelola master produk internal CV. Dewi Aditya (DA): kategori, model, varian/SKU,
          BOM (Bill of Material), dan ukuran. Terpisah dari Buyer Catalog Maklon.
        </p>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full max-w-3xl grid-cols-6">
          <TabsTrigger value="models" className="flex items-center gap-1.5" data-testid="tab-models">
            <Shirt className="w-3.5 h-3.5" />
            Model DA
          </TabsTrigger>
          <TabsTrigger value="categories" className="flex items-center gap-1.5" data-testid="tab-categories">
            <Tags className="w-3.5 h-3.5" />
            Kategori
          </TabsTrigger>
          <TabsTrigger value="variants" className="flex items-center gap-1.5" data-testid="tab-variants">
            <Boxes className="w-3.5 h-3.5" />
            Varian
          </TabsTrigger>
          <TabsTrigger value="bom" className="flex items-center gap-1.5" data-testid="tab-bom">
            <ListTree className="w-3.5 h-3.5" />
            BOM
          </TabsTrigger>
          <TabsTrigger value="sizes" className="flex items-center gap-1.5" data-testid="tab-sizes">
            <Ruler className="w-3.5 h-3.5" />
            Size
          </TabsTrigger>
          <TabsTrigger value="colors" className="flex items-center gap-1.5" data-testid="tab-colors">
            <Palette className="w-3.5 h-3.5" />
            Warna
          </TabsTrigger>
        </TabsList>

        <TabsContent value="models" className="mt-4">
          <RahazaModelsModule
            token={token}
            user={user}
            headers={headers}
            userRole={userRole}
            hasPerm={hasPerm}
            onNavigate={onNavigate}
          />
        </TabsContent>

        <TabsContent value="categories" className="mt-4">
          <RahazaProductCategoriesModule token={token} />
        </TabsContent>

        <TabsContent value="variants" className="mt-4">
          <RahazaVariantsModule token={token} />
        </TabsContent>

        <TabsContent value="bom" className="mt-4">
          <RahazaBOMModuleV2
            token={token}
            user={user}
            headers={headers}
            userRole={userRole}
            hasPerm={hasPerm}
            onNavigate={onNavigate}
          />
        </TabsContent>

        <TabsContent value="sizes" className="mt-4">
          <RahazaSizesModule
            token={token}
            user={user}
            headers={headers}
            userRole={userRole}
            hasPerm={hasPerm}
            onNavigate={onNavigate}
          />
        </TabsContent>

        <TabsContent value="colors" className="mt-4">
          <RahazaColorsModule token={token} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
