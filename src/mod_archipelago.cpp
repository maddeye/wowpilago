#include "APDelivery.h"
#include "APMerchant.h"
#include "APProgression.h"

void Addmod_archipelagoScripts()
{
    WoWPilago::RegisterProgressionScripts();
    WoWPilago::RegisterDeliveryScripts();
    WoWPilago::RegisterMerchantScripts();
}
