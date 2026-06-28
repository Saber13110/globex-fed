import { ShipmentSummary } from '../../core/services/chatbot.service';

/** Carte colis dans le chat : uniquement carte interactive ou bouton POD. */
export function shouldShowShipmentCardInChat(shipment: ShipmentSummary | null | undefined): boolean {
  if (!shipment) {
    return false;
  }
  if (shipment.sandbox_whitelist_denied) {
    return true;
  }
  if (shipment.show_tracking_map) {
    return true;
  }
  if (shipment.pod_available) {
    return true;
  }
  return false;
}
